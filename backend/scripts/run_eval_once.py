"""One-off Phase 15 evaluation smoke runner (dev DB). Prints per-case verdicts."""
import json
import sys

from app.db.session import SessionLocal
from app.eval.dataset import ground_truth_cases
from app.eval.service import EvaluationService
from app.knowledge.service import KnowledgeService
from app.services.seed_service import SeedService
from app.services.world_gen import world_dataset


def main():
    judge = sys.argv[1] if len(sys.argv) > 1 else "rule"
    db = SessionLocal()
    try:
        SeedService(db).seed_all(world_dataset())
        KnowledgeService(db).seed_catalog()
        result = EvaluationService(db).run_evaluation(judge=judge, note="dev smoke")
        run_id = result["eval_run_id"]
        detail = EvaluationService(db).get_run(run_id)
        for case in detail["cases"]:
            mark = "PASS" if case["passed"] else "FAIL"
            pred = case.get("prediction") or {}
            extra = []
            if pred.get("intent"):
                extra.append("intent=%s" % pred["intent"])
            if pred.get("primary_cause"):
                extra.append("primary=%s" % pred["primary_cause"])
            if pred.get("candidate_codes"):
                extra.append("cands=%s" % ",".join(pred["candidate_codes"]))
            if pred.get("parsed_action"):
                extra.append("action=%s" % pred["parsed_action"])
            if "followup_memory" in pred:
                extra.append("mem=%s" % len(pred["followup_memory"]))
            hall = case["metrics"].get("hallucination")
            if hall:
                extra.append("HALLUC=%s" % json.dumps(hall, ensure_ascii=False))
            print("[%s] %-28s %-10s %s" % (mark, case["case_id"], case["case_type"], " ".join(extra)))
        print(json.dumps(result["metrics"], ensure_ascii=False, default=str, indent=2))
    finally:
        db.close()


if __name__ == "__main__":
    main()
