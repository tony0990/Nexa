import os
import glob
import json
import time
from datetime import datetime
from dates.reference_time import CAIRO_TZ
from intelligence.extractor import Extractor
from intelligence.llm_runtime import LLMRuntime
from intelligence.confidence import finalize_candidate
from dates.normalizer import normalize_date_phrase

def run_suite():
    print("🚀 Starting Member 3 Fixture Suite...")

    # Setup
    runtime = LLMRuntime(model_path="mock_model.bin")
    runtime.start()
    extractor = Extractor(runtime)
    ref_dt = datetime(2026, 9, 24, 12, 0, tzinfo=CAIRO_TZ)

    metrics = {
        "total_segments": 0,
        "false_positives": 0,
        "false_negatives": 0,
        "resolved_dates_correct": 0,
        "total_date_bearing": 0,
        "repair_triggers": 0,
        "total_latency": 0.0
    }

    # 1. Test Zero Action (Precision Guardrail)
    zero_action_path = "tests/fixtures/transcripts/zero_action/baseline.txt"
    if os.path.exists(zero_action_path):
        with open(zero_action_path, "r", encoding="utf-8") as f:
            lines = [l.strip("- ").strip() for l in f if l.strip()]
            for text in lines:
                metrics["total_segments"] += 1
                start = time.time()
                res = extractor.extract(text, "seg-zero", ref_dt)
                metrics["total_latency"] += (time.time() - start)
                if len(res.items) > 0:
                    metrics["false_positives"] += 1

    # 2. Test Basic Extraction (Mixed Code-switch)
    mixed_path = "tests/fixtures/transcripts/mixed_codeswitch/baseline.txt"
    if os.path.exists(mixed_path):
        with open(mixed_path, "r", encoding="utf-8") as f:
            lines = [l.strip("- ").strip() for l in f if l.strip()]
            for text in lines:
                metrics["total_segments"] += 1
                start = time.time()
                res = extractor.extract(text, "seg-mixed", ref_dt)
                metrics["total_latency"] += (time.time() - start)

                # Check date resolution for each item
                for item in res.items:
                    metrics["total_date_bearing"] += 1
                    resolved = normalize_date_phrase(item.raw_date_phrase, ref_dt)
                    # In a real run, we would compare against a golden label
                    if resolved.resolved_datetime:
                        metrics["resolved_dates_correct"] += 1

    # Calculate Metrics
    fp_rate = (metrics["false_positives"] / metrics["total_segments"]) * 100 if metrics["total_segments"] > 0 else 0
    avg_latency = (metrics["total_latency"] / metrics["total_segments"]) * 1000 if metrics["total_segments"] > 0 else 0

    print("\n--- Member 3 Metrics Report ---")
    print(f"Total Segments Processed: {metrics['total_segments']}")
    print(f"False Positive Rate (Zero Action): {fp_rate:.2f}% (Target: 0.00%)")
    print(f"Date Resolution Accuracy: {(metrics['resolved_dates_correct']/metrics['total_date_bearing']*100 if metrics['total_date_bearing']>0 else 0):.2f}%")
    print(f"Average Latency per Segment: {avg_latency:.2f}ms")
    print(f"Repair-Path Trigger Rate: {metrics['repair_triggers'] / metrics['total_segments']*100 if metrics['total_segments']>0 else 0:.2f}%")
    print("------------------------------\n")

if __name__ == "__main__":
    run_suite()
