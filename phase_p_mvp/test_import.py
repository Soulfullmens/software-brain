try:
    from controller.planner import score_chunk_relevance
    print("Import successful")
except Exception as e:
    import traceback
    traceback.print_exc()
