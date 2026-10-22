from __future__ import annotations
import hashlib, json
from datetime import datetime, timezone
from .canonical import canonical_json, sha256_json
from .formal_domain import WikiSnapshotRead

STATES={"requested","in_progress","store_ready","reconciliation_required","succeeded","failed"}
class WikiFormalizationResult:
    def __init__(self,status,reason_code,formal_wiki_revision_id=None,operation_id=None,commit_hash=None):
        self.status=status; self.reason_code=reason_code; self.formal_wiki_revision_id=formal_wiki_revision_id; self.operation_id=operation_id; self.commit_hash=commit_hash

class WikiFormalizationService:
    def __init__(self,*,sqlite_store,terminus_store,terminus_database,resource_review_service=None,notifier=None,owner_authorization_verifier=None):
        self.db,self.store,self.database,self.resources,self.notifier=sqlite_store,terminus_store,terminus_database,resource_review_service,notifier
        self.owner_authorization_verifier=owner_authorization_verifier

    def formalize(self,merge_request_id,operation_id):
        with self.db.connection() as c:
            mr=c.execute("SELECT * FROM wiki_merge_request_buffer WHERE merge_request_id=?",(merge_request_id,)).fetchone()
            prior=c.execute("SELECT * FROM wiki_formalization_operation WHERE operation_id=?",(operation_id,)).fetchone()
        if prior and prior['merge_request_id'] != merge_request_id:
            return WikiFormalizationResult('failed','operation_id_conflict',operation_id=operation_id)
        if prior:
            with self.db.connection() as c:
                current=c.execute("SELECT * FROM wiki_merge_request_buffer WHERE merge_request_id=?",(merge_request_id,)).fetchone()
            if not current or any(prior[key] != current[column] for key,column in (("owner_event_id","owner_event_id"),("candidate_head","candidate_head"),("base_formal_revision_id","base_formal_revision_id"))):
                return WikiFormalizationResult('failed','operation_id_conflict',operation_id=operation_id)
        if prior and prior['state']=='succeeded':
            return WikiFormalizationResult('reconciliation_required','activation_evidence_unverified',operation_id=operation_id,commit_hash=prior['commit_hash'])
        if not mr or mr['status']!='approved' or not mr['owner_event_id']:
            return self._persist(operation_id,merge_request_id,'failed','owner_approval_required')
        try:
            authorized = self.owner_authorization_verifier is not None and self.owner_authorization_verifier.verify_owner(mr['owner_id'], mr['wiki_domain_id']) is True
        except Exception:
            authorized = False
        if not authorized:
            return self._persist(operation_id,merge_request_id,'failed','owner_authorization_unverified')
        if self.db.get_current_formal_revision_id(mr['wiki_domain_id'])!=mr['base_formal_revision_id']:
            return self._persist(operation_id,merge_request_id,'failed','stale_base')
        base=self.db.get_formal_revision(mr['base_formal_revision_id'])
        with self.db.connection() as c:
            cand=c.execute("SELECT * FROM wiki_candidate_commit WHERE candidate_commit_id=?",(mr['candidate_commit_id'],)).fetchone()
        if not base or not cand: return self._persist(operation_id,merge_request_id,'failed','candidate_missing')
        docs=self._read(cand['terminus_store_id'],cand['branch_id'],mr['candidate_head'])
        if docs is None: return self._persist(operation_id,merge_request_id,'reconciliation_required','candidate_unavailable')
        approvals=self._resource_approvals(docs)
        if approvals is None: return self._persist(operation_id,merge_request_id,'failed','resource_qualification_required')
        if prior and prior['resource_approval_ids'] and json.loads(prior['resource_approval_ids']) != approvals:
            return self._persist(operation_id,merge_request_id,'failed','resource_qualification_changed',approvals=approvals)
        if prior and prior['commit_hash']:
            marker_check=getattr(self.store,'verify_formalization_commit',None)
            try: marker_verified=callable(marker_check) and marker_check(prior['store_id'],self.database,prior['branch_id'],prior['commit_hash'],operation_id) is True
            except Exception: marker_verified=False
            if not marker_verified: return self._persist(operation_id,merge_request_id,'reconciliation_required','formal_commit_marker_unverified',prior['store_id'],prior['branch_id'],prior['commit_hash'],approvals)
            outcome={"status":"confirmed","store_id":prior["store_id"],"branch_id":prior["branch_id"],"commit_hash":prior["commit_hash"]}
        else:
            self._persist(operation_id,merge_request_id,'in_progress','attempt_started')
            try: outcome=self.store.create_formal_snapshot({"store_id":cand['terminus_store_id'],"database":self.database,"branch_id":cand['branch_id'],"commit_hash":mr['candidate_head']},operation_id)
            except Exception: outcome={"status":"unknown"}
            if not isinstance(outcome,dict): outcome=outcome.__dict__
            if outcome.get('status')!='confirmed': return self._persist(operation_id,merge_request_id,'reconciliation_required' if outcome.get('status')=='unknown' else 'failed',outcome.get('reason_code','store_result_unknown'))
        store,branch,commit=outcome.get('store_id'),outcome.get('branch_id'),outcome.get('commit_hash')
        formal_docs=self._read(store,branch,commit)
        expected_formal_docs=[dict(doc, lifecycle_state="formal") if doc.get("@type")=="WikiRevision" else doc for doc in docs]
        if formal_docs is None or sha256_json(formal_docs)!=sha256_json(expected_formal_docs): return self._persist(operation_id,merge_request_id,'reconciliation_required','formal_snapshot_unverified',store,branch,commit,approvals)
        if self.db.get_current_formal_revision_id(mr['wiki_domain_id'])!=mr['base_formal_revision_id']:
            return self._persist(operation_id,merge_request_id,'failed','stale_base',store,branch,commit,approvals)
        if self._resource_approvals(docs)!=approvals: return self._persist(operation_id,merge_request_id,'failed','resource_qualification_changed',store,branch,commit,approvals)
        formal_revision_ids = [
            str(doc.get("wiki_revision_id")) for doc in docs
            if doc.get("@type") == "WikiRevision"
            and doc.get("lifecycle_state") == "candidate"
            and doc.get("wiki_revision_id")
        ]
        if len(formal_revision_ids) != 1:
            return self._persist(operation_id,merge_request_id,'failed','candidate_revision_identity_invalid')
        revision=formal_revision_ids[0]
        result='wiki-formal-result-'+hashlib.sha256(operation_id.encode()).hexdigest()[:20]
        now=_now()
        try:
            with self.db.connection() as c:
                c.execute('BEGIN IMMEDIATE')
                current=c.execute('SELECT current_formal_revision_id FROM wiki_current_formal_revision WHERE wiki_domain_id=?',(mr['wiki_domain_id'],)).fetchone()
                if not current or current[0]!=mr['base_formal_revision_id']: raise ValueError('stale base')
                if self._resource_approvals(docs)!=approvals: raise ValueError('resource qualification changed')
                c.execute('INSERT INTO formal_wiki_revision VALUES (?,?,?,?,?,?)',(revision,mr['wiki_domain_id'],store,branch,commit,sha256_json(formal_docs)))
                c.execute('UPDATE wiki_current_formal_revision SET current_formal_revision_id=? WHERE wiki_domain_id=? AND current_formal_revision_id=?',(revision,mr['wiki_domain_id'],mr['base_formal_revision_id']))
                if c.execute('SELECT changes()').fetchone()[0]!=1: raise ValueError('stale base')
                c.execute("INSERT INTO wiki_formalization_result (result_id,wiki_domain_id,formal_wiki_revision_id,terminus_store_id,formal_commit_hash,result_status,resource_approval_map) VALUES (?,?,?,?,?,?,?)",(result,mr['wiki_domain_id'],revision,store,commit,'succeeded',json.dumps(approvals,sort_keys=True)))
                c.execute("INSERT INTO wiki_audit_event VALUES (?,?,?,?,?,?,?,?,?,?)",('wiki-audit-'+hashlib.sha256((operation_id+':activated').encode()).hexdigest()[:20],now,mr['owner_id'],'formalization_activated','WikiMergeRequestBuffer',merge_request_id,'succeeded','formalization_activated',json.dumps({'formal_revision_id':revision,'commit_hash':commit}),None))
                c.execute("UPDATE wiki_proposal SET status='merged' WHERE proposal_id=?",(mr['proposal_id'],))
                c.execute("UPDATE wiki_merge_request_buffer SET status='merged' WHERE merge_request_id=?",(merge_request_id,))
                op_attempt=c.execute("SELECT attempt_number FROM wiki_formalization_operation WHERE operation_id=?",(operation_id,)).fetchone()
                successful_attempt=(op_attempt[0]+1 if op_attempt else 1)
                c.execute("INSERT INTO wiki_formalization_operation (operation_id,merge_request_id,state,attempt_number,formal_revision_id,store_id,branch_id,commit_hash,reason_code,resource_approval_ids,owner_event_id,candidate_head,base_formal_revision_id,notification_status,notification_reason,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(operation_id) DO UPDATE SET state=excluded.state,attempt_number=excluded.attempt_number,store_id=COALESCE(excluded.store_id,store_id),branch_id=COALESCE(excluded.branch_id,branch_id),commit_hash=COALESCE(excluded.commit_hash,commit_hash),reason_code=excluded.reason_code,resource_approval_ids=excluded.resource_approval_ids,owner_event_id=COALESCE(owner_event_id,excluded.owner_event_id),candidate_head=COALESCE(candidate_head,excluded.candidate_head),base_formal_revision_id=COALESCE(base_formal_revision_id,excluded.base_formal_revision_id),updated_at=excluded.updated_at",(operation_id,merge_request_id,'succeeded',successful_attempt,revision,store,branch,commit,None,json.dumps(approvals,sort_keys=True),mr['owner_event_id'],mr['candidate_head'],mr['base_formal_revision_id'],'pending',None,now))
                c.commit()
        except Exception as exc:
            return self._persist(operation_id,merge_request_id,'reconciliation_required','sqlite_activation_unknown' if not isinstance(exc,ValueError) else 'activation_blocked',store,branch,commit,approvals)
        if self.notifier:
            try: self.notifier(merge_request_id,revision)
            except Exception:
                self._notification_failed(operation_id,merge_request_id,revision)
        return WikiFormalizationResult('succeeded','activated',revision,operation_id,commit)

    def _notification_failed(self, operation_id, merge_request_id, revision):
        now=_now()
        with self.db.connection() as c:
            c.execute("UPDATE wiki_formalization_operation SET notification_status='failed',notification_reason='notification_failed' WHERE operation_id=?",(operation_id,))
            event='wiki-audit-'+hashlib.sha256((operation_id+':notification_failed').encode()).hexdigest()[:20]
            c.execute("INSERT OR IGNORE INTO wiki_audit_event VALUES (?,?,?,?,?,?,?,?,?,?)",(event,now,'system','formalization_notification','WikiMergeRequestBuffer',merge_request_id,'failed','notification_failed',json.dumps({'formal_revision_id':revision,'operation_id':operation_id}),None))
            c.commit()

    def reconcile(self,operation_id):
        with self.db.connection() as c: row=c.execute('SELECT * FROM wiki_formalization_operation WHERE operation_id=?',(operation_id,)).fetchone()
        if not row: return WikiFormalizationResult('reconciliation_required','operation_missing',operation_id=operation_id)
        if not row: return WikiFormalizationResult('reconciliation_required','operation_missing',operation_id=operation_id)
        with self.db.connection() as c:
            activated=c.execute("SELECT r.formal_wiki_revision_id,r.terminus_store_id,r.formal_branch_id,r.formal_commit_hash,r.content_snapshot_digest, f.result_status, f.resource_approval_map, m.status AS mr_status, m.proposal_id, m.owner_event_id, m.candidate_head, m.base_formal_revision_id, p.status AS proposal_status, current.current_formal_revision_id FROM formal_wiki_revision r JOIN wiki_formalization_result f ON f.formal_wiki_revision_id=r.formal_wiki_revision_id JOIN wiki_merge_request_buffer m ON m.merge_request_id=? JOIN wiki_proposal p ON p.proposal_id=m.proposal_id JOIN wiki_current_formal_revision current ON current.wiki_domain_id=r.wiki_domain_id WHERE r.formal_wiki_revision_id=? AND r.wiki_domain_id=? AND r.terminus_store_id=? AND r.formal_branch_id=? AND r.formal_commit_hash=?",(row['merge_request_id'],row['formal_revision_id'],_domain_for_merge_request(self.db,row['merge_request_id']),row['store_id'],row['branch_id'],row['commit_hash'])).fetchone()
        if activated and activated['current_formal_revision_id']==activated['formal_wiki_revision_id'] and activated['mr_status']=='merged' and activated['proposal_status']=='merged' and activated['owner_event_id']==row['owner_event_id'] and activated['candidate_head']==row['candidate_head'] and activated['base_formal_revision_id']==row['base_formal_revision_id'] and activated['result_status']=='succeeded':
            docs=self._read(row['store_id'],row['branch_id'],row['commit_hash'])
            if docs is not None and sha256_json(docs)==activated['content_snapshot_digest']:
                return WikiFormalizationResult('succeeded','activation_reconciled',row['formal_revision_id'],operation_id,row['commit_hash'])
        if row['state']=='succeeded': return WikiFormalizationResult('reconciliation_required','activation_evidence_unverified',operation_id=operation_id,commit_hash=row['commit_hash'])
        return WikiFormalizationResult('reconciliation_required','write_reconciliation_required',operation_id=operation_id,commit_hash=row['commit_hash'])

    def _resource_approvals(self,docs):
        refs=[d for d in docs if d.get('@type')=='ResourceReference' and d.get('target_resource_version_id')]
        if not refs: return {}
        if self.resources is None: return None
        approvals={}
        for ref in refs:
            try: q=self.resources.get_current_qualification(ref['target_resource_version_id'],ref.get('requested_scope') or ref.get('reference_role'))
            except Exception: return None
            scope=ref.get('requested_scope') or ref.get('reference_role')
            if q.status!='approved' or not q.review_id or (q.use_scope and scope not in q.use_scope): return None
            approvals[ref['target_resource_version_id']]=q.review_id
        return dict(sorted(approvals.items()))
    def _read(self,store,branch,commit):
        try: r=self.store.read_exact_snapshot(store,self.database,branch,commit)
        except Exception: return None
        if not isinstance(r,WikiSnapshotRead) or r.status!='confirmed' or (r.store_id,r.database,r.branch_id,r.commit_hash)!=(store,self.database,branch,commit): return None
        return list(r.documents)
    def _persist(self,op,mr,state,reason,store=None,branch=None,commit=None,approvals=()):
        now=_now()
        with self.db.connection() as c:
            old=c.execute('SELECT * FROM wiki_formalization_operation WHERE operation_id=?',(op,)).fetchone()
            mr_row=c.execute('SELECT owner_event_id,candidate_head,base_formal_revision_id FROM wiki_merge_request_buffer WHERE merge_request_id=?',(mr,)).fetchone()
            if old and old['merge_request_id'] != mr:
                return WikiFormalizationResult('failed','operation_id_conflict',operation_id=op)
            if old and mr_row and any(old[key] and old[key] != mr_row[key] for key in ('owner_event_id','candidate_head','base_formal_revision_id')):
                return WikiFormalizationResult('failed','operation_id_conflict',operation_id=op)
            attempt=(old['attempt_number']+1 if old else 1)
            c.execute("INSERT INTO wiki_formalization_operation (operation_id,merge_request_id,state,attempt_number,formal_revision_id,store_id,branch_id,commit_hash,reason_code,resource_approval_ids,owner_event_id,candidate_head,base_formal_revision_id,notification_status,notification_reason,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(operation_id) DO UPDATE SET state=excluded.state,attempt_number=excluded.attempt_number,store_id=COALESCE(excluded.store_id,store_id),branch_id=COALESCE(excluded.branch_id,branch_id),commit_hash=COALESCE(excluded.commit_hash,commit_hash),reason_code=excluded.reason_code,resource_approval_ids=excluded.resource_approval_ids,owner_event_id=COALESCE(owner_event_id,excluded.owner_event_id),candidate_head=COALESCE(candidate_head,excluded.candidate_head),base_formal_revision_id=COALESCE(base_formal_revision_id,excluded.base_formal_revision_id),updated_at=excluded.updated_at",(op,mr,state,attempt,None,store,branch,commit,reason,json.dumps(approvals,sort_keys=True),mr_row['owner_event_id'] if mr_row else None,mr_row['candidate_head'] if mr_row else None,mr_row['base_formal_revision_id'] if mr_row else None,'not_sent',None,now))
            event='wiki-audit-'+hashlib.sha256((op+':'+str(attempt)+':'+reason).encode()).hexdigest()[:20]
            c.execute("INSERT OR IGNORE INTO wiki_audit_event VALUES (?,?,?,?,?,?,?,?,?,?)",(event,now,'system','formalization_state', 'WikiMergeRequestBuffer',mr,state,reason,json.dumps({'operation_id':op,'attempt':attempt,'commit_hash':commit}),None))
            c.commit()
        return WikiFormalizationResult(state,reason,operation_id=op,commit_hash=commit)
def _domain_for_merge_request(db,merge_request_id):
    with db.connection() as c:
        row=c.execute('SELECT wiki_domain_id FROM wiki_merge_request_buffer WHERE merge_request_id=?',(merge_request_id,)).fetchone()
    return row['wiki_domain_id'] if row else None

def _now(): return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
