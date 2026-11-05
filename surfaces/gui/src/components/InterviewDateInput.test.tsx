import {useState} from "react";
import {cleanup,fireEvent,render,screen} from "@testing-library/react";
import {afterEach,expect,it} from "vitest";
import {InterviewDateInput} from "./InterviewDateInput";
afterEach(cleanup);
it("moves from four-digit year to two-digit month/day, validates leap days, and clears old errors",()=>{
 function Form(){const [date,setDate]=useState<string|null>(null);return <form><InterviewDateInput value={date} onChange={setDate}/><output>{date}</output><button>保存</button></form>;}
 const {container}=render(<Form/>);
 const year=screen.getByLabelText("面试日期年"),month=screen.getByLabelText("面试日期月"),day=screen.getByLabelText("面试日期日");
 fireEvent.change(year,{target:{value:"2026"}});expect(document.activeElement).toBe(month);
 fireEvent.change(month,{target:{value:"02"}});expect(document.activeElement).toBe(day);
 fireEvent.change(day,{target:{value:"30"}});expect(container.querySelector("form")!.checkValidity()).toBe(false);
 fireEvent.change(day,{target:{value:"28"}});expect(screen.getByRole("status").textContent).toContain("2026-02-28T00:00:00+08:00");expect(container.querySelector("form")!.checkValidity()).toBe(true);
 fireEvent.click(screen.getByRole("button",{name:"清空日期"}));expect(container.querySelector("form")!.checkValidity()).toBe(true);
});
