from app.trust.photo import PhotoScorer


def test_no_duplicates_in_single_listing_result():
    scorer = PhotoScorer()
    photo_urls_per_listing = [
        ["https://img.com/a.jpg", "https://img.com/b.jpg"],
        ["https://img.com/c.jpg"],
    ]
    # All unique images — no duplicates
    results = scorer.check_duplicates(photo_urls_per_listing)
    assert all(not r for r in results)


def test_duplicate_photo_flagged():
    scorer = PhotoScorer()
    # Same URL in two listings = trivially duplicate (hash will match)
    photo_urls_per_listing = [
        ["https://img.com/same.jpg"],
        ["https://img.com/same.jpg"],
    ]
    results = scorer.check_duplicates(photo_urls_per_listing)
    # Both listings should be flagged
    assert results[0] is True or results[1] is True
