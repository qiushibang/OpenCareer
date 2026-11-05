"""Public personal-application service acceptance, using isolated local storage."""
from extensions.career_mcp.config import CareerConfig
from extensions.career_mcp.services.applications import Applications


def test_manual_application_is_independent_and_survives_restart(tmp_path):
    config = CareerConfig(tmp_path / "career")
    service = Applications(config)
    app = service.create({"company": "示例公司", "title": "AI产品实习生", "location": "北京", "jd": "完整岗位职责", "notes": "保留原始备注"})
    assert app["status"] == "preparing"
    assert Applications(config).get(app["id"])["notes"] == "保留原始备注"
    other = service.create({"company": "示例公司", "title": "策略产品经理", "location": "上海"})
    assert other["id"] != app["id"]
    assert service.list()["total"] == 2


def test_resume_version_is_owned_and_retained_as_metadata_after_original_removal(tmp_path):
    from extensions.career_mcp.services.resumes import ResumeService
    config=CareerConfig(tmp_path / "career")
    resumes=ResumeService(config,private_root=tmp_path / "private")
    proposal={"basic":{"name":"测试同学","phone":None,"email":None,"location":None,"summary":None},"education":[],"experience":[],"project":[],"skill":[],"missing_fields":[],"warnings":[]}
    ids=[]
    for name,text in [("产品简历一版.txt","测试同学：产品经历"),("产品简历二版.txt","测试同学：产品与评测经历")]:
        staged=resumes.stage_resume(filename=name,mime="text/plain",text=text*10)
        preview=resumes.preview_resume_import(staged["upload_token"],proposal)
        resumes.confirm_resume_sections(preview["preview_token"],["basic"])
        ids.append(next(row["id"] for row in resumes.list_resume_documents() if row["display_name"]==name))
    service=Applications(config)
    app=service.create({"company":"示例","title":"产品","resume_import_id":ids[0]})
    updated=service.update(app["id"],{"expected_version":app["version"],"resume_import_id":ids[1],"resume_label":app["resume_label"]})
    assert updated["resume_label"] == "产品简历二版.txt"
    fingerprint=updated["resume_sha256"]
    resumes.delete_resume_document(ids[1],confirm_name="产品简历二版.txt")
    saved=service.update(app["id"],{"expected_version":updated["version"],"notes":"原件移除后仍可记面经"})
    assert saved["resume_label"] == "产品简历二版.txt" and saved["resume_sha256"] == fingerprint
    assert "测试同学：产品与评测经历" not in str(service.export({}))


def test_legacy_progress_is_migrated_once_and_both_editing_entries_stay_consistent(tmp_path):
    from extensions.career_mcp.crawler.adapters import FakeAdapter
    from extensions.career_mcp.domain.crawler import JobSnapshot
    from extensions.career_mcp.services.crawler import CrawlerService
    from extensions.career_mcp.services.jobs import JobService
    from extensions.career_mcp.services.job_tracking import JobTrackingService
    config = CareerConfig(tmp_path / "career")
    CrawlerService(config).crawl(FakeAdapter("fixture", [JobSnapshot("one", "产品经理", "当时的完整JD", "https://example.com/one", "2026-10-30T01:00:00Z", "北京", "experienced")]))
    job = JobService(config).search_jobs()["jobs"][0]
    tracking = JobTrackingService(config)
    tracking.update(job["id"], {"expected_version": 0, "is_favorite": True, "application_status": "interviewing", "note": "原进度备注\n不能丢失"})
    service = Applications(config)
    first = service.get(service.list()["records"][0]["id"])
    assert first["status"] == "interviewing" and first["stage"] == ""
    assert first["notes"] == "原进度备注\n不能丢失"
    assert service.create({"job_id": job["id"]})["id"] == first["id"]
    assert service.list()["total"] == 1
    original_applied_at = tracking.get(job["id"])["applied_at"]
    saved = service.update(first["id"], {"expected_version": first["version"], "status": "offer", "notes": "新的完整备注"})
    assert tracking.get(job["id"])["application_status"] == "offer"
    assert tracking.get(job["id"])["is_favorite"] is True
    assert tracking.get(job["id"])["applied_at"] == original_applied_at
    old = tracking.get(job["id"])
    tracking.update(job["id"], {"expected_version": old["version"], "note": "从旧入口编辑"})
    assert service.get(saved["id"])["notes"] == "从旧入口编辑"
    assert service.get(saved["id"])["jd"] == "当时的完整JD"


def test_rounds_keep_their_own_outcome_and_long_review_and_export_all_pages(tmp_path):
    import pytest
    service = Applications(CareerConfig(tmp_path / "career"))
    app = service.create({"company": "示例", "title": "产品", "jd": "很长的JD\n" * 6000})
    first = service.save_interview(app["id"], {"round_name": "业务一面", "arrangement": "completed", "result": "pending", "questions": "=HYPERLINK(\"https://example.com\")", "review": "真实面经\n" * 9000})
    second = service.save_interview(app["id"], {"round_name": "业务二面", "arrangement": "scheduled", "scheduled_at": "2026-11-02T14:00:00+08:00", "set_current_stage": True})
    assert first["result"] == "pending"
    saved = service.get(app["id"])
    assert saved["status"] == "interviewing" and saved["stage"] == "业务二面"
    assert len(saved["interviews"]) == 2
    assert saved["interviews"][0]["review"] == "真实面经\n" * 9000
    with pytest.raises(ValueError, match="VERSION_CONFLICT"):
        service.update(app["id"], {"expected_version": app["version"], "notes": "过期编辑"})
    for i in range(52):
        service.create({"company": "其他", "title": f"岗位{i}"})
    assert len(service.list(limit=20)["records"]) == 20
    exported = service.export({})
    assert len(exported["applications"]) == 53
    assert service.export({"filters": {"company": "示例"}})["applications"][0]["jd"] == "很长的JD\n" * 6000
    assert service.export({"ids": [app["id"]]})["interviews"][0]["review"] == "真实面经\n" * 9000
    assert second["scheduled_at"] == "2026-11-02T06:00:00Z"


def test_v14_upgrade_retains_old_notes_history_and_favorites(tmp_path):
    from extensions.career_mcp.crawler.adapters import FakeAdapter
    from extensions.career_mcp.domain.crawler import JobSnapshot
    from extensions.career_mcp.services.crawler import CrawlerService
    from extensions.career_mcp.services.jobs import JobService
    from extensions.career_mcp.services.job_tracking import JobTrackingService
    from extensions.career_mcp.database.migrations import connect
    config = CareerConfig(tmp_path / "career")
    CrawlerService(config).crawl(FakeAdapter("old", [JobSnapshot("1","旧岗位","旧JD","https://example.com/1","2026-10-28T00:00:00Z")]))
    job = JobService(config).search_jobs()["jobs"][0]
    tracking = JobTrackingService(config)
    tracking.update(job["id"], {"expected_version":0,"is_favorite":True,"application_status":"interviewing","note":"旧版本已有的备注"})
    # External migration fixture: v14 contains the original tracking tables only.
    with connect(config.database_path) as db:
        db.execute("DROP TABLE career_application_history")
        db.execute("DROP TABLE career_application_interviews")
        db.execute("DROP TABLE career_applications")
        db.execute("DELETE FROM schema_migrations WHERE version=15")
        db.execute("PRAGMA user_version=14")
    old = tracking.get(job["id"])
    assert old["note"] == "旧版本已有的备注"
    app = Applications(config).get(Applications(config).list()["records"][0]["id"])
    assert app["notes"] == old["note"] and app["stage"] == ""
    assert app["applied_date_source"] == "legacy_tracking"
    assert any(event["event_type"] == "legacy_status" for event in app["history"])
    assert Applications(config).list()["total"] == 1
    assert tracking.get(job["id"])["is_favorite"] is True


def test_favorites_stay_separate_and_catalog_changes_do_not_overwrite_private_snapshot(tmp_path):
    from extensions.career_mcp.crawler.adapters import FakeAdapter
    from extensions.career_mcp.domain.crawler import JobSnapshot
    from extensions.career_mcp.services.crawler import CrawlerService
    from extensions.career_mcp.services.jobs import JobService
    from extensions.career_mcp.services.job_tracking import JobTrackingService
    config=CareerConfig(tmp_path / "career")
    crawl=CrawlerService(config)
    crawl.crawl(FakeAdapter("fixture",[JobSnapshot("1","原岗位","原始JD","https://example.com/1","2026-10-28T00:00:00Z")]))
    job=JobService(config).search_jobs()["jobs"][0]
    JobTrackingService(config).update(job["id"],{"expected_version":0,"is_favorite":True,"note":"收藏笔记"})
    service=Applications(config)
    assert service.list()["total"] == 0
    app=service.create({"job_id":job["id"]})
    assert app["notes"] == "收藏笔记"
    crawl.crawl(FakeAdapter("fixture",[JobSnapshot("1","官网后来改名","后来JD","https://example.com/1","2026-10-30T00:00:00Z")]))
    assert service.get(app["id"])["jd"] == "原始JD"
    again=service.create({"job_id":job["id"],"new_attempt":True})
    assert again["id"] != app["id"] and service.list()["total"] == 2
    assert service.get(app["id"])["notes"] == "收藏笔记"
    crawl.crawl(FakeAdapter("fixture",[]))
    crawl.crawl(FakeAdapter("fixture",[]))
    assert service.get(app["id"])["jd"] == "原始JD"
    assert service.list()["total"] == 2


def test_official_fields_read_only_and_simplified_fields_preserve_legacy(tmp_path):
    import pytest
    from extensions.career_mcp.crawler.adapters import FakeAdapter
    from extensions.career_mcp.domain.crawler import JobSnapshot
    from extensions.career_mcp.services.crawler import CrawlerService
    from extensions.career_mcp.services.jobs import JobService
    config=CareerConfig(tmp_path/"career")
    CrawlerService(config).crawl(FakeAdapter("fixture",[JobSnapshot("one","产品经理","官网JD","https://example.com/one","2026-10-30T01:00:00Z","北京","experienced")]))
    job=JobService(config).search_jobs()["jobs"][0]
    service=Applications(config)
    with pytest.raises(ValueError,match="官网岗位信息不可修改"):
        service.create({"job_id":job["id"],"title":"伪造"})
    app=service.create({"job_id":job["id"],"salary_expected":"历史期望","resume_label":"原简历名称"})
    for key in ("company","title","location","recruitment_type","department","business_line","source_url","jd"):
        with pytest.raises(ValueError):
            service.update(app["id"],{"expected_version":app["version"],key:"用户修改"})
    saved=service.update(app["id"],{"expected_version":app["version"],"monthly_salary":"25000","stage":"二面"})
    assert saved["salary_expected"]=="历史期望" and saved["resume_label"]=="原简历名称" and saved["jd"]=="官网JD"
    old=service.save_interview(app["id"],{"round_name":"业务一面","questions":"原问题","review":"原复盘"})
    updated=service.save_interview(app["id"],{"expected_version":old["version"],"experience_notes":"单一面经"},old["id"])
    assert updated["questions"]=="原问题" and updated["review"]=="原复盘" and updated["experience_notes"]=="单一面经"
    cleared=service.save_interview(app["id"],{"expected_version":updated["version"],"experience_notes":""},old["id"])
    assert cleared["experience_notes"]=="" and cleared["review"]=="原复盘"


def test_monthly_salary_times_months_is_derived_and_exported_without_guessing(tmp_path):
    import pytest
    service=Applications(CareerConfig(tmp_path/'career'))
    app=service.create({'company':'示例','title':'产品','monthly_salary':'25k','salary_months':14,'next_action':'旧待办不丢失'})
    assert app['annual_salary']=='350000'
    assert service.list()['records'][0]['annual_salary']=='350000'
    assert service.export({})['applications'][0]['annual_salary']=='350000'
    saved=service.update(app['id'],{'expected_version':app['version'],'monthly_salary':'2.5万','salary_months':16})
    assert saved['annual_salary']=='400000' and saved['next_action']=='旧待办不丢失'
    with pytest.raises(ValueError):service.update(app['id'],{'expected_version':saved['version'],'salary_months':0})
    with pytest.raises(ValueError):service.update(app['id'],{'expected_version':saved['version'],'annual_salary':'999999'})
    unknown=service.update(app['id'],{'expected_version':saved['version'],'monthly_salary':'面议'})
    assert unknown['annual_salary']==''
