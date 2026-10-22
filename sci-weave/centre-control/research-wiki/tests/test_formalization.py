from __future__ import annotations
import tempfile, unittest
from pathlib import Path
from llm_wiki.formalization import WikiFormalizationService
from llm_wiki.formal_domain import WikiSnapshotRead
from llm_wiki.sqlite_store import SqliteStore
from llm_wiki.canonical import sha256_json

class Store:
    def __init__(self): self.writes=[]
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
