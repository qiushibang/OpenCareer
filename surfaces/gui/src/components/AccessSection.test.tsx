import {afterEach,expect,it,vi} from "vitest";
import {cleanup,fireEvent,render,screen,waitFor} from "@testing-library/react";
import {AccessSection} from "./AccessSection";
const state=vi.hoisted(()=>({web:false,local:false,connections:vi.fn(),connectors:vi.fn(),toggle:vi.fn(),add:vi.fn(),folderToggle:vi.fn()}));
vi.mock('../api',()=>({isAlpha:()=>state.web,isLocal:()=>state.local,CLOUD_CHANGED:'cloud',getSessionConnections:state.connections,getConnectors:state.connectors,getSubscriptions:async()=>[],getRecentChannels:async()=>[],getCloudStatus:async()=>({signed_in:false}),setSessionConnection:state.toggle}));
vi.mock('../useRoots',()=>({useRoots:()=>({roots:[{path:'/example/resumes',label:'简历资料',primary:false,writable:false,exists:true}],busy:false,error:'',addRoot:state.add,toggleAccess:state.folderToggle,removeRoot:vi.fn()})}));
afterEach(()=>{cleanup();vi.clearAllMocks();state.web=false;state.local=false;});
function desktop(){state.connections.mockResolvedValue({connected:[{connector:'browser',enabled:true,detail:'Browser'}],recommended:[]});state.connectors.mockResolvedValue([{name:'browser',title:'Browser',available:true,fields:[],instructions:[],blurb:'Browser'}]);state.toggle.mockResolvedValue({ok:true});}
it('does not advertise unavailable desktop grants in Career web builds',()=>{
 state.web=true;const {container}=render(<AccessSection sessionId="test"/>);expect(container.textContent).toBe('');expect(state.connections).not.toHaveBeenCalled();expect(state.connectors).not.toHaveBeenCalled();
});
it('uses clear Chinese labels and preserves session-only switches and read-only folder defaults',async()=>{
 desktop();const manage=vi.fn();render(<AccessSection sessionId="test" onOpenIntegrations={manage}/>);fireEvent.click(screen.getByTestId('access-toggle'));
 expect(await screen.findByText('浏览器',{exact:true})).toBeTruthy();expect(screen.queryByText('Browser',{exact:true})).toBeNull();
 expect(screen.getByText('工具与服务')).toBeTruthy();fireEvent.click(screen.getByRole('switch'));await waitFor(()=>expect(state.toggle).toHaveBeenCalledWith('test','browser',false));
 fireEvent.click(screen.getByRole('button',{name:'管理已连接的服务 →'}));expect(manage).toHaveBeenCalledOnce();
 fireEvent.click(screen.getByRole('button',{name:'+ 添加可访问文件夹'}));expect((screen.getByRole('checkbox',{name:'允许写入'}) as HTMLInputElement).checked).toBe(false);
 expect(screen.getByRole('button',{name:'只读'})).toBeTruthy();expect(state.add).not.toHaveBeenCalled();
});

it('exposes the reviewed controls in the local browser build',async()=>{desktop();state.web=true;state.local=true;render(<AccessSection sessionId="local"/>);fireEvent.click(screen.getByTestId('access-toggle'));expect(await screen.findByText('浏览器',{exact:true})).toBeTruthy();expect(screen.getByRole('button',{name:'+ 添加可访问文件夹'})).toBeTruthy();});
