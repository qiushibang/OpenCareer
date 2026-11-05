import {useState} from "react";
import {cleanup,fireEvent,render,screen} from "@testing-library/react";
import {afterEach,expect,it,vi} from "vitest";
import {DateInput} from "./DateInput";
afterEach(cleanup);
it("constrains the year, advances segments and rejects impossible dates before committing",()=>{
 const commit=vi.fn();function Form(){const [value,setValue]=useState<string|null>(null);return <form><DateInput label="投递日期" value={value} onChange={setValue} onCommit={commit}/><output>{value}</output></form>;}
 const {container}=render(<Form/>);const year=screen.getByLabelText("投递日期年"),month=screen.getByLabelText("投递日期月"),day=screen.getByLabelText("投递日期日");
 fireEvent.change(year,{target:{value:"202611"}});expect(year).toHaveProperty("value","2026");expect(document.activeElement).toBe(month);
 fireEvent.change(month,{target:{value:"02"}});expect(document.activeElement).toBe(day);
 fireEvent.change(day,{target:{value:"30"}});fireEvent.blur(day);expect(container.querySelector("form")!.checkValidity()).toBe(false);expect(commit).not.toHaveBeenCalled();
 fireEvent.change(day,{target:{value:"28"}});fireEvent.blur(day);expect(container.querySelector("form")!.checkValidity()).toBe(true);expect(commit).toHaveBeenCalledExactlyOnceWith("2026-02-28");
 fireEvent.blur(day);expect(commit).toHaveBeenCalledTimes(1);
});
it("uses the selected month, selects real dates, and restores focus on Escape",()=>{
 const change=vi.fn(),commit=vi.fn();render(<DateInput label="日期" value="2024-02-20" onChange={change} onCommit={commit}/>);
 const trigger=screen.getByRole("button",{name:"日期选择日期"});fireEvent.click(trigger);
 expect(screen.getByRole("dialog",{name:"日期日历"})).toBeTruthy();fireEvent.click(screen.getByRole("button",{name:"2024-02-29"}));expect(change).toHaveBeenCalledWith("2024-02-29");expect(commit).toHaveBeenCalledExactlyOnceWith("2024-02-29");expect(screen.queryByRole("dialog")).toBeNull();
 fireEvent.click(trigger);fireEvent.keyDown(document,{key:"Escape"});expect(screen.queryByRole("dialog")).toBeNull();expect(document.activeElement).toBe(trigger);
});
it("clears incomplete dates without submitting invalid data",()=>{
 const change=vi.fn();render(<DateInput label="日期" value={null} onChange={change}/>);fireEvent.change(screen.getByLabelText("日期年"),{target:{value:"20"}});fireEvent.click(screen.getByRole("button",{name:"日期选择日期"}));fireEvent.click(screen.getByRole("button",{name:"清空日期"}));expect(change).toHaveBeenCalledWith(null);expect(screen.getByLabelText("日期年")).toHaveProperty("value","");
});
