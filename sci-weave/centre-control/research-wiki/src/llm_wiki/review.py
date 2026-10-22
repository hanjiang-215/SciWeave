from __future__ import annotations
import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

from .canonical import canonical_json, sha256_json
from .formal_domain import WikiSnapshotRead

class OwnerAuthorizationVerifier:
    def verify_owner(self, actor_id: str, wiki_domain_id: str) -> bool: ...

@dataclass(frozen=True)
class WikiReviewResult:
    status: str
    reason_code: str
    preview_id: str | None = None
    proposal_id: str | None = None
    base_formal_revision_id: str | None = None
    candidate_head: str | None = None
    evidence: tuple = ()

@dataclass(frozen=True)
class WikiDecisionResult:
    status: str
    reason_code: str
    audit_event_id: str | None = None

class WikiReviewService:
    def __init__(self, *, sqlite_store, terminus_store, terminus_database, resource_review_service=None, owner_authorization_verifier=None):
        self.db, self.store, self.database, self.resources = sqlite_store, terminus_store, terminus_database, resource_review_service
        self.owner_authorization_verifier = owner_authorization_verifier

    def preview(self, proposal_id):
        with self.db.connection() as c:
            proposal=c.execute("SELECT * FROM wiki_proposal WHERE proposal_id=?",(proposal_id,)).fetchone()
            candidate=c.execute("SELECT * FROM wiki_candidate_commit WHERE proposal_id=?",(proposal_id,)).fetchone()
        if not proposal or not candidate: return WikiReviewResult("unavailable","proposal_missing")
        if self.db.get_current_formal_revision_id(proposal['wiki_domain_id']) != proposal['base_formal_revision_id']:
            return WikiReviewResult("stale_base","stale_base",proposal_id=proposal_id,base_formal_revision_id=proposal['base_formal_revision_id'],candidate_head=candidate['commit_hash'])
        head_reader = getattr(self.store, "read_branch_head", None)
        if callable(head_reader):
            try:
                current_head = head_reader(candidate['terminus_store_id'], self.database, candidate['branch_id'])
            except Exception:
                current_head = None
            if current_head != candidate['commit_hash']:
                return WikiReviewResult("stale_candidate", "candidate_head_changed", proposal_id=proposal_id, base_formal_revision_id=proposal['base_formal_revision_id'], candidate_head=candidate['commit_hash'])
        base=self.db.get_formal_revision(proposal['base_formal_revision_id'])
        reads=[]
        for store,branch,commit in ((candidate['terminus_store_id'],candidate['branch_id'],candidate['commit_hash']),(base.terminus_store_id,base.formal_branch_id,base.formal_commit_hash)):
            try: reads.append(self.store.read_exact_snapshot(store,self.database,branch,commit))
            except Exception: reads.append(None)
        cand, old=reads
        if not all(isinstance(r,WikiSnapshotRead) and r.status=="confirmed" for r in reads):
            return WikiReviewResult("unavailable","snapshot_unavailable",proposal_id=proposal_id)
        if (old.store_id,old.database,old.branch_id,old.commit_hash)!=(base.terminus_store_id,self.database,base.formal_branch_id,base.formal_commit_hash):
            return WikiReviewResult("unavailable","base_snapshot_mismatch",proposal_id=proposal_id)
        if (cand.store_id,cand.database,cand.branch_id,cand.commit_hash)!=(candidate['terminus_store_id'],self.database,candidate['branch_id'],candidate['commit_hash']):
            return WikiReviewResult("candidate_mismatch","candidate_mismatch",proposal_id=proposal_id)
        old_by={_key(d):d for d in old.documents}; new_by={_key(d):d for d in cand.documents}
        changes=[]
        for key in sorted(set(old_by)|set(new_by)):
            if old_by.get(key)!=new_by.get(key): changes.append({"object":key,"before":old_by.get(key),"after":new_by.get(key)})
        conflict = _has_object_conflicts(old.documents, cand.documents)
        evidence=tuple(changes)
        pid="wiki-preview-"+hashlib.sha256((proposal_id+candidate['commit_hash']+proposal['base_formal_revision_id']+sha256_json(changes)).encode()).hexdigest()[:20]
        return WikiReviewResult("conflict" if conflict else "ready", "object_conflict" if conflict else "no_conflicts",pid,proposal_id,proposal['base_formal_revision_id'],candidate['commit_hash'],evidence)

    def create_merge_request(self, proposal_id, merge_request_id, reviewer_id):
        p=self.preview(proposal_id)
        if p.status!="ready": return p
        now=_now(); audit="wiki-audit-"+hashlib.sha256((merge_request_id+"locked").encode()).hexdigest()[:20]
        with self.db.connection() as c:
            c.execute("BEGIN IMMEDIATE")
            c.execute("INSERT INTO wiki_merge_request_buffer (merge_request_id,proposal_id,wiki_domain_id,base_formal_revision_id,candidate_head,candidate_commit_id,status,reviewer_id,owner_id,owner_decision,owner_event_id,created_at,locked_preview_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",(merge_request_id,proposal_id,_domain(self.db,proposal_id),p.base_formal_revision_id,p.candidate_head,_candidate_id(self.db,proposal_id),"ready_for_owner",reviewer_id,None,"pending",None,now,p.preview_id))
            c.execute("INSERT INTO wiki_review_evidence VALUES (?,?,?,?,?)",(p.preview_id,merge_request_id,canonical_json(list(p.evidence)),p.reason_code,now))
            c.execute("INSERT INTO wiki_audit_event VALUES (?,?,?,?,?,?,?,?,?,?)",(audit,now,reviewer_id,"wiki_review_completed","WikiMergeRequestBuffer",merge_request_id,"completed",p.reason_code,canonical_json({"preview_id":p.preview_id}),None)); c.commit()
        return WikiReviewResult("ready_for_owner","locked",p.preview_id,proposal_id,p.base_formal_revision_id,p.candidate_head,p.evidence)

    def decide(self, merge_request_id, *, actor_id, decision, reason, selected_solution_id):
        if decision not in ("approved","rejected") or not actor_id or not reason: return WikiDecisionResult("rejected","invalid_decision")
        with self.db.connection() as c:
            mr=c.execute("SELECT * FROM wiki_merge_request_buffer WHERE merge_request_id=?",(merge_request_id,)).fetchone()
        if not mr: return WikiDecisionResult("rejected","merge_request_missing")
        if not self._candidate_head_matches(mr):
            return WikiDecisionResult("rejected", "candidate_head_changed")
        try:
            authorized = self.owner_authorization_verifier is not None and self.owner_authorization_verifier.verify_owner(actor_id, mr['wiki_domain_id']) is True
        except Exception:
            authorized = False
        if not authorized: return WikiDecisionResult("rejected", "owner_authorization_unverified")
        approval_ids={}
        if decision=="approved":
            if selected_solution_id!=mr['candidate_commit_id']: return WikiDecisionResult("rejected","solution_mismatch")
            if self.db.get_current_formal_revision_id(mr['wiki_domain_id'])!=mr['base_formal_revision_id']: return WikiDecisionResult("rejected","stale_base")
            refs=self._references(mr['candidate_commit_id'],mr['candidate_head'])
            if refs is None: return WikiDecisionResult("rejected","candidate_unavailable")
            if refs:
                if self.resources is None: return WikiDecisionResult("rejected","resource_qualification_required")
                for ref in refs:
                    try: qualification=self.resources.get_current_qualification(ref['target_resource_version_id'],ref.get('requested_scope') or ref.get('reference_role'))
                    except Exception: return WikiDecisionResult("rejected","resource_qualification_required")
                    scope=ref.get('requested_scope') or ref.get('reference_role')
                    if qualification.status!='approved' or not qualification.review_id or (qualification.use_scope and scope not in qualification.use_scope): return WikiDecisionResult("rejected","resource_qualification_required")
                    approval_ids[ref['target_resource_version_id']]=qualification.review_id
        status="approved" if decision=="approved" else "rejected"; event="wiki-owner-"+hashlib.sha256((merge_request_id+actor_id+decision+reason).encode()).hexdigest()[:20]; now=_now()
        with self.db.connection() as c:
            c.execute("BEGIN IMMEDIATE")
            latest=c.execute("SELECT status,owner_event_id FROM wiki_merge_request_buffer WHERE merge_request_id=?",(merge_request_id,)).fetchone()
            if latest is None or latest['status'] not in ('ready_for_owner','approved','rejected','reapproval_required'):
                c.rollback()
                return WikiDecisionResult("rejected","merge_request_state_invalid")
            c.execute("UPDATE wiki_merge_request_buffer SET status=?,owner_id=?,owner_decision=?,owner_event_id=?,owner_resource_approval_ids=? WHERE merge_request_id=?",(status,actor_id,decision,event,canonical_json(approval_ids),merge_request_id))
            c.execute("INSERT INTO wiki_audit_event VALUES (?,?,?,?,?,?,?,?,?,?)",(event,now,actor_id,"owner_formal_publication_review","WikiMergeRequestBuffer",merge_request_id,decision,"owner_decision",canonical_json({"reason":reason,"selected_solution_id":selected_solution_id}),None)); c.commit()
        return WikiDecisionResult(status,"owner_decision_recorded",event)

    def _candidate_head_matches(self, mr):
        with self.db.connection() as c:
            row=c.execute("SELECT terminus_store_id,branch_id FROM wiki_candidate_commit WHERE candidate_commit_id=?",(mr['candidate_commit_id'],)).fetchone()
        reader=getattr(self.store,"read_branch_head",None)
        if not row or not callable(reader): return False
        try: return reader(row['terminus_store_id'],self.database,row['branch_id'])==mr['candidate_head']
        except Exception: return False

    def _references(self, candidate_id, commit):
        try:
            with self.db.connection() as c: row=c.execute("SELECT terminus_store_id,branch_id,commit_hash FROM wiki_candidate_commit WHERE candidate_commit_id=?",(candidate_id,)).fetchone()
            if not row or row['commit_hash'] != commit: return None
            read=self.store.read_exact_snapshot(row['terminus_store_id'],self.database,row['branch_id'],commit)
            return [d for d in read.documents if d.get('@type')=='ResourceReference'] if read.status=='confirmed' and (read.store_id,read.database,read.branch_id,read.commit_hash)==(row['terminus_store_id'],self.database,row['branch_id'],commit) else None
        except Exception: return None
    def _eligible(self, ref):
        try:
            q=self.resources.get_current_qualification(ref['target_resource_version_id'],ref.get('requested_scope') or ref.get('reference_role'))
            return q.status=='approved' and q.review_id and (not q.use_scope or (ref.get('requested_scope') or ref.get('reference_role')) in q.use_scope)
        except Exception: return False

def _has_object_conflicts(base_documents, candidate_documents):
    """Reject snapshots containing conflicting copies of one logical object.

    Wiki revisions are keyed by revision id; resource references by reference id.
    Repeated keys are only acceptable when their full canonical document agrees.
    """
    for documents in (base_documents, candidate_documents):
        seen = {}
        for document in documents:
            if not isinstance(document, dict):
                return True
            key = _key(document)
            serialized = canonical_json(document)
            if key in seen and seen[key] != serialized:
                return True
            seen[key] = serialized
    return False

def _key(d): return d.get('wiki_revision_id') or d.get('reference_id') or d.get('@id') or json.dumps(d,sort_keys=True)
def _now(): return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
def _domain(db,p):
    with db.connection() as c: return c.execute('SELECT wiki_domain_id FROM wiki_proposal WHERE proposal_id=?',(p,)).fetchone()[0]
def _candidate_id(db,p):
    with db.connection() as c: return c.execute('SELECT candidate_commit_id FROM wiki_candidate_commit WHERE proposal_id=?',(p,)).fetchone()[0]
