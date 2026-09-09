"""URL parser for Comic Vine links."""

import re
from typing import Optional


# Pattern: comicvine.gamespot.com/<slug>/<TYPE>-<ID>/
# Types: 4000 = issue, 4050 = volume/series
CV_URL_PATTERN = re.compile(
    r"comicvine\.gamespot\.com/[^/]+/(\d{4}-\d+)/?",
    re.IGNORECASE
)


def _parse_cv_id(full_id: str) -> dict[str, Optional[str]]:
    """
    Parse a Comic Vine ID string into series_id and issue_id.
    
    Args:
        full_id: String like "4000-139720" or "4050-23227"
        
    Returns:
        Dict with 'series_id' and 'issue_id' (both Optional[str])
    """
    result = {"series_id": None, "issue_id": None}
    
    if "-" not in full_id:
        return result
    
    type_prefix, id_number = full_id.split("-", 1)
    
    # 4000 = issue, 4050 = volume/series
    if type_prefix == "4000":
        result["issue_id"] = id_number
    elif type_prefix == "4050":
        result["series_id"] = id_number
    
    return result


def extract_comicvine_ids(url: str) -> dict[str, Optional[str]]:
    """
    Extract series_id and issue_id from a Comic Vine URL.
    
    Args:
        url: Comic Vine URL like https://comicvine.gamespot.com/doctor-strange/4000-139720/
        
    Returns:
        Dict with 'series_id' and 'issue_id' (both Optional[str])
    """
    match = CV_URL_PATTERN.search(url)
    if not match:
        return {"series_id": None, "issue_id": None}
    
    return _parse_cv_id(match.group(1))


def extract_all_cv_ids(text: str) -> list[dict[str, Optional[str]]]:
    """
    Extract all Comic Vine IDs from text (e.g., from ComicInfo.xml Web/Notes fields).
    
    Args:
        text: Text containing one or more Comic Vine URLs
        
    Returns:
        List of dicts with 'series_id' and 'issue_id'
    """
    results = []
    for match in CV_URL_PATTERN.finditer(text):
        results.append(_parse_cv_id(match.group(1)))
    return results
