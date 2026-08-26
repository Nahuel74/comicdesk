"""URL parser for Comic Vine links."""

import re
from typing import Optional


# Pattern: comicvine.gamespot.com/<slug>/<TYPE>-<ID>/
# Types: 4000 = issue, 4050 = volume/series
CV_URL_PATTERN = re.compile(
    r"comicvine\.gamespot\.com/[^/]+/(\d{4}-\d+)/?",
    re.IGNORECASE
)


def extract_comicvine_ids(url: str) -> dict[str, Optional[str]]:
    """
    Extract series_id and issue_id from a Comic Vine URL.
    
    Args:
        url: Comic Vine URL like https://comicvine.gamespot.com/doctor-strange/4000-139720/
        
    Returns:
        Dict with 'series_id' and 'issue_id' (both Optional[str])
    """
    result = {"series_id": None, "issue_id": None}
    
    match = CV_URL_PATTERN.search(url)
    if not match:
        return result
    
    full_id = match.group(1)  # e.g., "4000-139720"
    type_prefix, id_number = full_id.split("-", 1)
    
    # 4000 = issue, 4050 = volume/series
    if type_prefix == "4000":
        result["issue_id"] = id_number
    elif type_prefix == "4050":
        result["series_id"] = id_number
    
    return result


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
        full_id = match.group(1)
        type_prefix, id_number = full_id.split("-", 1)
        
        entry = {"series_id": None, "issue_id": None}
        if type_prefix == "4000":
            entry["issue_id"] = id_number
        elif type_prefix == "4050":
            entry["series_id"] = id_number
        
        results.append(entry)
    
    return results
