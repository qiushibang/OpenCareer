from extensions.career_mcp.domain.locations import split_job_locations


def test_split_job_locations_separates_composite_cities():
    assert split_job_locations(["北京、深圳、广州"]) == [
        "北京",
        "深圳",
        "广州",
    ]


def test_split_job_locations_normalizes_simple_city_suffix_and_deduplicates():
    assert split_job_locations(["北京市，上海市", "北京"]) == [
        "北京",
        "上海",
    ]


def test_split_job_locations_preserves_complex_administrative_text():
    assert split_job_locations(["浙江 拱墅区"]) == ["浙江 拱墅区"]
