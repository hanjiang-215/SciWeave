from __future__ import annotations
import tempfile, unittest
from pathlib import Path
from llm_wiki.formalization import WikiFormalizationService
from llm_wiki.formal_domain import WikiSnapshotRead
from llm_wiki.review import WikiReviewService
from llm_wiki.sqlite_store import SqliteStore
from llm_wiki.canonical import sha256_json

class Store:
    def __init__(self): self.writes=[]
    def read_branch_head(self, store, db, branch):
        return "candidate-head"
    def create_formal_snapshot(self, candidate_ref, operation_id):
        self.writes.append((candidate_ref,operation_id)); return {"status":"confirmed","store_id":"s","branch_id":"main","commit_hash":"formal-commit"}
    def read_exact_snapshot(self, store, db, branch, commit):
        docs=[{"@type":"WikiRevision","wiki_revision_id":"r2","title":"new","body_markdown":"body","lifecycle_state":"candidate"}]
        if commit == "formal-commit": docs[0]["lifecycle_state"]="formal"
        return WikiSnapshotRead.confirmed(store_id=store,database=db,branch_id=branch,commit_hash=commit,documents=docs,content_digest=sha256_json(docs))

class Formalization(unittest.TestCase):
    def test_success_requires_owner_authorization_verifier(self):
        with tempfile.TemporaryDirectory() as t:
            db=SqliteStore(str(Path(t)/"db")); db.initialize()
            db.add_formal_revision(formal_revision_id="base",wiki_domain_id="d",terminus_store_id="s",formal_branch_id="main",formal_commit_hash="base")
            db.set_current_formal_revision("d","base")
            with db.connection() as c:
                c.execute("INSERT INTO wiki_proposal VALUES (?,?,?,?,?,?,?,?)",("p","d","base","s","candidate","candidate","a","now"))
                c.execute("INSERT INTO wiki_candidate_commit VALUES (?,?,?,?,?,?,?,?,?,?,?)",("cc","d","p","s","candidate","candidate-head","base","digest","snapshot","a","now"))
                c.execute("INSERT INTO wiki_merge_request_buffer (merge_request_id,proposal_id,wiki_domain_id,base_formal_revision_id,candidate_head,candidate_commit_id,status,reviewer_id,owner_id,owner_decision,owner_event_id,created_at,locked_preview_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",("mr","p","d","base","candidate-head","cc","approved","owner","owner","approved","owner-event","now","preview")); c.commit()
            service=WikiFormalizationService(sqlite_store=db,terminus_store=Store(),terminus_database="wiki-db")
            self.assertEqual(service.formalize("mr","op").reason_code,"owner_authorization_unverified")

    def test_requires_owner_approval_and_activates_only_after_exact_store_readback(self):
        with tempfile.TemporaryDirectory() as t:
            db=SqliteStore(str(Path(t)/"db")); db.initialize()
            db.add_formal_revision(formal_revision_id="base",wiki_domain_id="d",terminus_store_id="s",formal_branch_id="main",formal_commit_hash="base")
            db.set_current_formal_revision("d","base")
            with db.connection() as c:
                c.execute("INSERT INTO wiki_proposal VALUES (?,?,?,?,?,?,?,?)",("p","d","base","s","candidate","candidate","a","now"))
                c.execute("INSERT INTO wiki_candidate_commit VALUES (?,?,?,?,?,?,?,?,?,?,?)",("cc","d","p","s","candidate","candidate-head","base","digest","snapshot","a","now")); c.commit()
            service=WikiFormalizationService(sqlite_store=db,terminus_store=Store(),terminus_database="wiki-db",notifier=lambda *_: (_ for _ in ()).throw(RuntimeError("transport down")))
            with db.connection() as c:
                c.execute("INSERT INTO wiki_merge_request_buffer (merge_request_id,proposal_id,wiki_domain_id,base_formal_revision_id,candidate_head,candidate_commit_id,status,reviewer_id,owner_id,owner_decision,owner_event_id,created_at,locked_preview_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",("mr","p","d","base","candidate-head","cc","approved","owner","owner","approved","owner-event","now","preview")); c.commit()
            service._persist("op", "other-mr", "failed", "owner_approval_required")
            rebound = service.formalize("mr", "op")
            self.assertEqual((rebound.status, rebound.reason_code), ("failed", "operation_id_conflict"))
            self.assertEqual(db.get_current_formal_revision_id("d"),"base")
            service.owner_authorization_verifier = type("Verifier", (), {"verify_owner": lambda self, actor, domain: actor == "owner" and domain == "d"})()
            result=service.formalize("mr","fresh-op")
            self.assertEqual(result.status,"succeeded",result.reason_code)
            with db.connection() as c:
                evidence = c.execute("SELECT r.formal_wiki_revision_id,r.terminus_store_id,r.formal_branch_id,r.formal_commit_hash,r.content_snapshot_digest,f.result_status,m.status,p.status,current.current_formal_revision_id FROM formal_wiki_revision r JOIN wiki_formalization_result f ON f.formal_wiki_revision_id=r.formal_wiki_revision_id JOIN wiki_merge_request_buffer m ON m.merge_request_id='mr' JOIN wiki_proposal p ON p.proposal_id=m.proposal_id JOIN wiki_current_formal_revision current ON current.wiki_domain_id=r.wiki_domain_id WHERE r.formal_wiki_revision_id='r2'").fetchone()
                self.assertIsNotNone(evidence)
                self.assertEqual(tuple(evidence[5:]), ('succeeded','merged','merged','r2'))
            self.assertEqual(service.formalize("mr", "fresh-op").status, "reconciliation_required")
            reconciled = service.reconcile("fresh-op")
            self.assertEqual((reconciled.status, reconciled.reason_code), ("succeeded", "activation_reconciled"))
            with db.connection() as c:
                self.assertEqual(c.execute("SELECT COUNT(*) FROM formal_wiki_revision WHERE formal_wiki_revision_id='r2'").fetchone()[0], 1)
            self.assertEqual(result.formal_wiki_revision_id, "r2")
            self.assertEqual(db.get_current_formal_revision_id("d"), "r2")
            with db.connection() as c:
                result_row=c.execute("SELECT * FROM wiki_formalization_result").fetchone()
                op_row=c.execute("SELECT notification_status,notification_reason FROM wiki_formalization_operation WHERE operation_id='fresh-op'").fetchone()
                audit_count=c.execute("SELECT COUNT(*) FROM wiki_audit_event WHERE target_id='mr' AND action='formalization_notification'").fetchone()[0]
                audit_actions={row[0] for row in c.execute("SELECT action FROM wiki_audit_event WHERE target_id='mr'").fetchall()}
            self.assertEqual(result_row["resource_approval_map"], "{}")
            with db.connection() as c:
                op_approvals=c.execute("SELECT resource_approval_ids FROM wiki_formalization_operation WHERE operation_id='fresh-op'").fetchone()[0]
            self.assertEqual(op_approvals, "{}")
            self.assertEqual((op_row["notification_status"],op_row["notification_reason"]),("failed","notification_failed"))
            self.assertGreaterEqual(audit_count,1)
            self.assertIn("formalization_activated",audit_actions)

    def test_prior_commit_without_operation_marker_proof_is_not_activated_or_rewritten(self):
        with tempfile.TemporaryDirectory() as t:
            db = _prepared_db(Path(t) / "db")
            store = Store()
            service = _service(db, store)
            with db.connection() as c:
                c.execute("INSERT INTO wiki_formalization_operation (operation_id,merge_request_id,state,attempt_number,store_id,branch_id,commit_hash,owner_event_id,candidate_head,base_formal_revision_id,resource_approval_ids,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", ("op","mr","reconciliation_required",1,"s","main","formal-commit","owner-event","candidate-head","base","{}","now"))
                c.commit()
            result = service.formalize("mr", "op")
            self.assertEqual(result.status, "reconciliation_required")
            self.assertEqual(db.get_current_formal_revision_id("d"), "base")
            self.assertEqual(store.writes, [])

    def test_reconcile_unknown_write_never_retries_snapshot_creation(self):
        with tempfile.TemporaryDirectory() as t:
            db = _prepared_db(Path(t) / "db")
            store = Store()
            store.create_formal_snapshot = lambda *_: (_ for _ in ()).throw(AssertionError("must not write during reconcile"))
            service = _service(db, store)
            service._persist("op", "mr", "reconciliation_required", "store_result_unknown")
            result = service.reconcile("op")
            self.assertEqual(result.status, "reconciliation_required")
            self.assertEqual(db.get_current_formal_revision_id("d"), "base")

    def test_same_operation_is_rejected_when_owner_approval_identity_changes(self):
        with tempfile.TemporaryDirectory() as t:
            db = _prepared_db(Path(t) / "db")
            store = Store()
            service = _service(db, store)
            first = service.formalize("mr", "op")
            self.assertEqual(first.status, "succeeded")
            with db.connection() as c:
                c.execute("UPDATE wiki_merge_request_buffer SET owner_event_id='new-owner-event' WHERE merge_request_id='mr'")
                c.commit()
            second = service.formalize("mr", "op")
            self.assertEqual((second.status, second.reason_code), ("failed", "operation_id_conflict"))
            self.assertEqual(len(store.writes), 1)

    def test_owner_reapproval_required_when_resource_approval_changes(self):
        with tempfile.TemporaryDirectory() as t:
            db = _prepared_db(Path(t) / "db")
            store = Store()
            resource_docs = [
                {"@type":"WikiRevision","wiki_revision_id":"r2","title":"new","body_markdown":"body","lifecycle_state":"candidate"},
                {"@type":"ResourceReference","reference_id":"ref","target_resource_version_id":"rv","requested_scope":"evidence"},
            ]
            store.read_exact_snapshot = lambda s,d,b,c: WikiSnapshotRead.confirmed(store_id=s,database=d,branch_id=b,commit_hash=c,documents=resource_docs if c == "candidate-head" else [{**resource_docs[0],"lifecycle_state":"formal"},resource_docs[1]],content_digest=sha256_json(resource_docs))
            store.read_branch_head = lambda *_: "candidate-head"
            class Resources:
                review_id = "review-1"
                def get_current_qualification(self, *_):
                    return type("Q", (), {"status":"approved","review_id":self.review_id,"use_scope":("evidence",)})()
            resources=Resources()
            service=WikiFormalizationService(sqlite_store=db,terminus_store=store,terminus_database="wiki-db",resource_review_service=resources,owner_authorization_verifier=type("V",(),{"verify_owner":lambda *_:True})())
            with db.connection() as c:
                c.execute("UPDATE wiki_merge_request_buffer SET owner_resource_approval_ids=? WHERE merge_request_id='mr'", ('{"rv":"review-1"}',))
                c.commit()
            resources.review_id="review-2"
            result=service.formalize("mr","new-op")
            self.assertEqual((result.status,result.reason_code),("failed","owner_reapproval_required"))
            self.assertEqual(store.writes, [])
            with db.connection() as c:
                mr = c.execute("SELECT status,owner_decision,owner_event_id,owner_resource_approval_ids FROM wiki_merge_request_buffer WHERE merge_request_id='mr'").fetchone()
            self.assertEqual(tuple(mr), ("reapproval_required", "pending", None, "{}"))
            self.assertEqual(db.get_current_formal_revision_id("d"),"base")

    def test_resource_approval_change_requires_new_owner_decision_and_operation_identity(self):
        with tempfile.TemporaryDirectory() as t:
            db = _prepared_db(Path(t) / "db")
            store = Store()
            docs = [
                {"@type":"WikiRevision","wiki_revision_id":"r2","title":"new","body_markdown":"body","lifecycle_state":"candidate"},
                {"@type":"ResourceReference","reference_id":"ref","target_resource_version_id":"rv","requested_scope":"evidence"},
            ]
            def read_snapshot(store_id, database, branch, commit):
                snapshot = docs if commit == "candidate-head" else [
                    {**docs[0], "lifecycle_state":"formal"}, docs[1]
                ]
                return WikiSnapshotRead.confirmed(
                    store_id=store_id, database=database, branch_id=branch,
                    commit_hash=commit, documents=snapshot,
                    content_digest=sha256_json(snapshot),
                )
            store.read_exact_snapshot = read_snapshot
            class Resources:
                review_id = "review-1"
                def get_current_qualification(self, *_):
                    return type("Q", (), {"status":"approved", "review_id":self.review_id, "use_scope":("evidence",)})()
            resources = Resources()
            verifier = type("Verifier", (), {"verify_owner":lambda self, actor, domain: actor == "owner" and domain == "d"})()
            formalizer = WikiFormalizationService(
                sqlite_store=db, terminus_store=store, terminus_database="wiki-db",
                resource_review_service=resources, owner_authorization_verifier=verifier,
            )
            reviewer = WikiReviewService(
                sqlite_store=db, terminus_store=store, terminus_database="wiki-db",
                resource_review_service=resources, owner_authorization_verifier=verifier,
            )
            with db.connection() as c:
                c.execute("UPDATE wiki_merge_request_buffer SET owner_resource_approval_ids=? WHERE merge_request_id='mr'", ('{"rv":"review-1"}',))
                c.commit()

            resources.review_id = "review-2"
            revoked = formalizer.formalize("mr", "old-operation")
            self.assertEqual((revoked.status, revoked.reason_code), ("failed", "owner_reapproval_required"))
            self.assertEqual(store.writes, [])
            with db.connection() as c:
                mr = c.execute("SELECT status,owner_decision,owner_event_id,owner_resource_approval_ids FROM wiki_merge_request_buffer WHERE merge_request_id='mr'").fetchone()
            self.assertEqual(tuple(mr), ("reapproval_required", "pending", None, "{}"))

            renewed = reviewer.decide(
                "mr", actor_id="owner", decision="approved", reason="resource approval renewed",
                selected_solution_id="cc",
            )
            self.assertEqual((renewed.status, renewed.reason_code), ("approved", "owner_decision_recorded"))
            with db.connection() as c:
                fresh_event = c.execute("SELECT owner_event_id,owner_resource_approval_ids FROM wiki_merge_request_buffer WHERE merge_request_id='mr'").fetchone()
            self.assertTrue(fresh_event[0])
            self.assertEqual(fresh_event[1], '{"rv":"review-2"}')

            old_reuse = formalizer.formalize("mr", "old-operation")
            self.assertEqual((old_reuse.status, old_reuse.reason_code), ("failed", "operation_id_conflict"))
            self.assertEqual(store.writes, [])
            completed = formalizer.formalize("mr", "new-operation")
            self.assertEqual((completed.status, completed.reason_code), ("succeeded", "activated"))
            self.assertEqual(completed.operation_id, "new-operation")
            self.assertEqual(len(store.writes), 1)
            with db.connection() as c:
                op = c.execute("SELECT owner_event_id,resource_approval_ids,state FROM wiki_formalization_operation WHERE operation_id='new-operation'").fetchone()
            self.assertEqual(tuple(op), (fresh_event[0], '{"rv": "review-2"}', "succeeded"))

    def test_attempt_number_increases_for_each_operation_state_record(self):
        with tempfile.TemporaryDirectory() as t:
            db = _prepared_db(Path(t) / "db")
            service = _service(db, Store())
            service._persist("op", "mr", "reconciliation_required", "first")
            service._persist("op", "mr", "reconciliation_required", "second")
            with db.connection() as c:
                row = c.execute("SELECT attempt_number FROM wiki_formalization_operation WHERE operation_id='op'").fetchone()
            self.assertEqual(row[0], 2)

    def test_sqlite_activation_rollback_preserves_no_partial_formalization_or_missing_audit(self):
        with tempfile.TemporaryDirectory() as t:
            db = _prepared_db(Path(t) / "db")
            service = _service(db, Store())
            with db.connection() as c:
                c.execute("CREATE TRIGGER reject_formalization_audit BEFORE INSERT ON wiki_audit_event WHEN NEW.action='formalization_activated' BEGIN SELECT RAISE(ABORT, 'audit unavailable'); END")
                c.commit()
            result = service.formalize("mr", "op")
            self.assertEqual(result.status, "reconciliation_required")
            with db.connection() as c:
                self.assertEqual(c.execute("SELECT COUNT(*) FROM formal_wiki_revision WHERE formal_wiki_revision_id!='base'").fetchone()[0], 0)
                self.assertEqual(c.execute("SELECT COUNT(*) FROM wiki_formalization_result").fetchone()[0], 0)
                self.assertEqual(c.execute("SELECT COUNT(*) FROM wiki_audit_event WHERE action='formalization_activated'").fetchone()[0], 0)
                self.assertEqual(c.execute("SELECT status FROM wiki_merge_request_buffer WHERE merge_request_id='mr'").fetchone()[0], "approved")
                self.assertEqual(c.execute("SELECT status FROM wiki_proposal WHERE proposal_id='p'").fetchone()[0], "candidate")


def _prepared_db(path):
    db = SqliteStore(str(path)); db.initialize()
    db.add_formal_revision(formal_revision_id="base",wiki_domain_id="d",terminus_store_id="s",formal_branch_id="main",formal_commit_hash="base")
    db.set_current_formal_revision("d","base")
    with db.connection() as c:
        c.execute("INSERT INTO wiki_proposal VALUES (?,?,?,?,?,?,?,?)",("p","d","base","s","candidate","candidate","a","now"))
        c.execute("INSERT INTO wiki_candidate_commit VALUES (?,?,?,?,?,?,?,?,?,?,?)",("cc","d","p","s","candidate","candidate-head","base","digest","snapshot","a","now"))
        c.execute("INSERT INTO wiki_merge_request_buffer (merge_request_id,proposal_id,wiki_domain_id,base_formal_revision_id,candidate_head,candidate_commit_id,status,reviewer_id,owner_id,owner_decision,owner_event_id,created_at,locked_preview_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",("mr","p","d","base","candidate-head","cc","approved","owner","owner","approved","owner-event","now","preview"))
        c.commit()
    return db

def _service(db, store):
    verifier = type("Verifier", (), {"verify_owner": lambda self, actor, domain: actor == "owner" and domain == "d"})()
    return WikiFormalizationService(sqlite_store=db, terminus_store=store, terminus_database="wiki-db", owner_authorization_verifier=verifier)

if __name__ == "__main__": unittest.main()
