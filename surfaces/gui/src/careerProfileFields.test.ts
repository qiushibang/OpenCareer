import { describe, expect, it } from "vitest";

import { careerProfileFieldLabel } from "./careerProfileFields";

describe("careerProfileFieldLabel", () => {
  it("labels imported basic fields and names by section", () => {
    expect(careerProfileFieldLabel("address")).toBe("地址");
    expect(careerProfileFieldLabel("city")).toBe("城市");
    expect(careerProfileFieldLabel("target_role")).toBe("目标岗位");
    expect(careerProfileFieldLabel("name", "basic")).toBe("姓名");
    expect(careerProfileFieldLabel("name", "project")).toBe("项目名称");
    expect(careerProfileFieldLabel("name", "skill")).toBe("技能名称");
  });
  it("translates known Career Vault fields", () => {
    expect(careerProfileFieldLabel("name")).toBe("姓名");
    expect(careerProfileFieldLabel("phone")).toBe("手机号");
    expect(careerProfileFieldLabel("email")).toBe("邮箱");
    expect(careerProfileFieldLabel("birth_date")).toBe("出生日期");
    expect(careerProfileFieldLabel("school")).toBe("学校");
    expect(careerProfileFieldLabel("degree")).toBe("学历");
    expect(careerProfileFieldLabel("major")).toBe("专业");
    expect(careerProfileFieldLabel("gpa")).toBe("GPA");
    expect(careerProfileFieldLabel("ranking")).toBe("排名");
    expect(careerProfileFieldLabel("start_date")).toBe("开始时间");
    expect(careerProfileFieldLabel("end_date")).toBe("结束时间");
    expect(careerProfileFieldLabel("company")).toBe("公司");
    expect(careerProfileFieldLabel("title")).toBe("职位");
    expect(careerProfileFieldLabel("project_name")).toBe("项目名称");
    expect(careerProfileFieldLabel("technologies")).toBe("技术栈");
    expect(careerProfileFieldLabel("level")).toBe("熟练程度");
    expect(careerProfileFieldLabel("evidence")).toBe("佐证");
  });

  it("makes unknown storage keys readable without changing values", () => {
    expect(careerProfileFieldLabel("custom_field")).toBe("custom field");
    expect(careerProfileFieldLabel("other-value")).toBe("other value");
  });
});
