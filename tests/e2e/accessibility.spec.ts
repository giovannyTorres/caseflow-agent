import {test,expect} from '../../apps/web/node_modules/@playwright/test';

test('confirmation returns keyboard focus to its trigger (view fixture)', async ({page}) => {
  const detail={id:'dialog-case',title:'Fixture approval dialog',scenario:'duplicate',status:'awaiting_approval',priority:'low',assignee:'analyst',amount:100,currency:'MXN',
    proposal:{version:1,amount:100,reason:'Synthetic evidence summary.',status:'awaiting_approval'},events:[],messages:[],movements:[],evidence:[],job:{id:'fixture-job',status:'waiting'}};
  await page.route('**/api/**',route=>{
    const pathname=new URL(route.request().url()).pathname;
    const body=pathname==='/api/config'?{mode:'DEMO',provider:'openai',model:'fixture',live_ready:false,missing:['OPENAI_API_KEY']}:
      pathname==='/api/me'?{username:'supervisor',role:'supervisor',mode:'DEMO'}:
      pathname==='/api/cases'?[detail]:detail;
    return route.fulfill({json:body});
  });
  await page.goto('/');
  await page.getByRole('button',{name:/Fixture approval dialog/}).click();
  const trigger=page.getByRole('button',{name:'Approve v1',exact:true});
  await trigger.click();
  await expect(page.getByRole('button',{name:'Cancel',exact:true})).toBeFocused();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await expect(trigger).toBeFocused();
});
