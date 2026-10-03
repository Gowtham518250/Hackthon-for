from app.chunking import chunk_document


def test_problem_table_becomes_atomic_chunks():
    text = """
[[SOURCE:page 2]]
1 Two Sum Easy Hash Map LeetCode #1
2 Contains Duplicate Easy Hash Set LeetCode #217
3 Valid Anagram Easy Hash Map / Counting LeetCode #242
6 Maximum Subarray Medium Kadane / DP LeetCode #53
"""
    chunks = chunk_document(text, ["page 2"])

    assert len(chunks) == 4
    assert chunks[0][2]["problem_number"] == 1
    assert chunks[0][2]["difficulty"] == "Easy"
    assert chunks[0][2]["leetcode"] == "LeetCode #1"
    assert chunks[-1][2]["difficulty"] == "Medium"
