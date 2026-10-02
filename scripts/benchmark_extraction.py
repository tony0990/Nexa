import time
from datetime import datetime
from nexa.dates.reference_time import CAIRO_TZ
from nexa.intelligence.extractor import Extractor
from nexa.intelligence.llm_runtime import LLMRuntime

def benchmark():
    print("⏱️ Starting Extraction Benchmark...")

    runtime = LLMRuntime(model_path="mock_model.bin")
    runtime.start()
    extractor = Extractor(runtime)
    ref_dt = datetime(2026, 9, 24, 12, 0, tzinfo=CAIRO_TZ)

    # Test cases: short, medium, long, and mixed
    test_cases = [
        "أحمد، ابعت التقرير بكرة",
        "سارة، جهزي الاجتماع يوم الخميس الساعة عشرة الصبح مع الفريق كله في المكتب",
        "نور، ابعتي الإيميل بكرة والملفات يوم الحد ومحمد يراجعهم قبل كده",
        "لازم نخلص الـ deployment before Friday and check the logs today"
    ]

    print(f"{'Text':<60} | {'Latency (ms)':<15} | {'Token Est.':<12}")
    print("-" * 90)

    total_lat = 0
    for text in test_cases:
        start = time.time()
        extractor.extract(text, "bench-1", ref_dt)
        lat = (time.time() - start) * 1000
        total_lat += lat
        # Mock token estimation based on length for the skeleton
        tokens = len(text.split()) * 1.3
        print(f"{text[:58]:<60} | {lat:<15.2f} | {tokens:<12.1f}")

    print("-" * 90)
    print(f"Average Latency: {total_lat/len(test_cases):.2f}ms")

if __name__ == "__main__":
    benchmark()
