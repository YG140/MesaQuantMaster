import { expect, test, type Page } from "@playwright/test";
import { http, HttpResponse } from "msw";
import { server } from "../tests/testServer";
import { policy, response } from "./fixtures/planejar";

const api = "http://127.0.0.1:8000";
const portfolio = {
  total_invested:"4600",total_market_value:"5000",total_profit:"400",profitability:"8.69565217",
  market_data_status:"live",quote_updated_at:"2026-09-11T12:00:00Z",unpriced_symbols:[],
  allocation:[{ticker:"PETR4",allocation:"40"},{ticker:"VALE3",allocation:"60"}],
  positions:[
    {asset_id:"asset-1",ticker:"PETR4",asset_name:"Petrobras PN",quantity:"100",average_price:"18",invested_amount:"1800",current_price:"20",market_value:"2000",unrealized_profit:"200",unrealized_profit_percent:"11.11111111",allocation:"40",weight:"40",valuation_basis:"market_value"},
    {asset_id:"asset-2",ticker:"VALE3",asset_name:"Vale ON",quantity:"100",average_price:"28",invested_amount:"2800",current_price:"30",market_value:"3000",unrealized_profit:"200",unrealized_profit_percent:"7.14285714",allocation:"60",weight:"60",valuation_basis:"market_value"},
  ],
};
const dashboard={patrimonio_total:"5000",valor_investido:"4600",lucro_prejuizo:"400",rentabilidade:"8.69565217",ativos:2,operacoes:2,market_data_status:"live",quote_updated_at:portfolio.quote_updated_at,unpriced_symbols:[]};
const intelligencePortfolio = {
  policy,
  overview: {current_equity:"5000",total_invested:"4600",profit_loss:"400",profitability:"8.69565217",received_income:null,investments_count:2,fixed_income_percentage:"0",variable_income_percentage:"100",portfolio_classification:"Carteira de renda variável",risk_level:"Alto",data_quality:"Parcial",last_updated_at:portfolio.quote_updated_at,market_data_status:"live",insufficient_data_message:"Dados insuficientes para calcular."},
  diagnosis: {portfolio_score:null,risk_level:"Alto",diversification_score:null,concentration_score:null,liquidity_score:null,income_score:null,data_quality:"Parcial",warnings:["Carteira concentrada em ações."],strengths:["Posições consolidadas."],weaknesses:["Indicadores insuficientes para calcular pontuações."],class_allocations:[{asset_class:"Ações",current_value:"5000",current_percentage:"100",target_percentage:"100",minimum_percentage:"80",maximum_percentage:"100",difference_percentage:"0",status:"Dentro da estratégia"}],unclassified_assets:[],calculated_at:portfolio.quote_updated_at},
  recommendations:[],
  rebalancing:[{asset_class:"Ações",current_percentage:"100",target_percentage:"100",difference_percentage:"0",current_value:"5000",target_value:"5000",suggested_contribution:"900",missing_value:"0",excess_value:"0",status:"Dentro da estratégia",explanation:"Classe alinhada à política determinística."}],
  opportunities:[],available_indicators:{},unavailable_indicators:{},generated_at:portfolio.quote_updated_at,
};
test.beforeAll(()=>server.listen({onUnhandledRequest:"error"}));
test.afterAll(()=>server.close());
test.afterEach(()=>server.resetHandlers());
test.beforeEach(async({page})=>{
  server.use(
    http.get(`${api}/portfolio`,()=>HttpResponse.json(portfolio)),
    http.get(`${api}/dashboard`,()=>HttpResponse.json(dashboard)),
    http.get(`${api}/intelligence/portfolio`,()=>HttpResponse.json(intelligencePortfolio)),
    http.get(`${api}/assets`,()=>HttpResponse.json(portfolio.positions.map(position=>({id:position.asset_id,ticker:position.ticker,name:position.asset_name,asset_type:"STOCK",sector:null,country:"BR",currency:"BRL",exchange:"B3",is_active:true,created_at:"2026-09-10T12:00:00Z",updated_at:portfolio.quote_updated_at})))),
    http.get(`${api}/intelligence/policy`,()=>HttpResponse.json(policy)),
    http.post(`${api}/intelligence/build-portfolio`,()=>HttpResponse.json(response)),
    http.get(`${api}/operations`,()=>HttpResponse.json(portfolio.positions.map((p,index)=>({id:`op-${index}`,asset_id:p.asset_id,brokerage_id:"brokerage-1",operation_type:"BUY",operation_date:"2026-09-10",quantity:p.quantity,unit_price:p.average_price,fees:"0",taxes:"0",notes:null})))),
  );
  await page.route(`${api}/**`,async route=>{
    const request=route.request();
    const result=await fetch(request.url(),{method:request.method(),headers:request.headers(),...(request.postData()?{body:request.postData()!}:{})});
    await route.fulfill({status:result.status,headers:Object.fromEntries(result.headers),body:await result.text()});
  });
  await page.addInitScript(()=>sessionStorage.setItem("mesa_quant_session","orbita-e2e-token"));
  await page.emulateMedia({reducedMotion:"reduce"});
});

async function capture(page:Page,name:string){
  const geometry=await page.locator("body").evaluate(body=>{
    const width=body.ownerDocument.documentElement.clientWidth;
    const outside=[...body.querySelectorAll("main h1,main h2,main h3,main td,main th,main input,main select,main button,main .qp-metric,main .qp-identity,main .recommended-asset,main .settings-section,main .settings-index a")].filter(element=>{
      const rect=element.getBoundingClientRect();return element.checkVisibility()&&rect.width>0&&rect.height>0&&(rect.left < -1||rect.right>width+1);
    }).map(element=>({tag:element.tagName,text:element.textContent?.slice(0,70),left:element.getBoundingClientRect().left,right:element.getBoundingClientRect().right}));
    const overflowing = [...body.querySelectorAll("*")].filter(element => element.checkVisibility() && element.getBoundingClientRect().right > width + 1).slice(0, 15).map(element => ({tag: element.tagName, class: element.getAttribute("class"), right: element.getBoundingClientRect().right}));
    return {clientWidth:width,scrollWidth:body.ownerDocument.documentElement.scrollWidth,outside,overflowing};
  });
  console.log(JSON.stringify({name,...geometry}));
  await page.screenshot({path:`test-results/orbita-${name}.png`,fullPage:false});
  expect.soft(geometry.scrollWidth,name).toBeLessThanOrEqual(geometry.clientWidth);
  expect.soft(geometry.outside,name).toEqual([]);
}

const screens=[
  {name:"inicio",path:"/",heading:"O que você quer fazer hoje?"},
  {name:"carteira",path:"/carteira",heading:"Minha carteira"},
  {name:"mercado",path:"/ativos",heading:"Mercado e ativos"},
  {name:"planejar",path:"/planejar",heading:"Inteligência de Carteira"},
  {name:"configuracoes",path:"/configuracoes",heading:"Conta e Perfil"},
];
async function openScreen(page: Page, path: string) {
  const profile = page.waitForResponse(result => result.url() === `${api}/investor-profile/status`);
  await page.goto(path);
  const result = await profile;
  expect(result.status()).toBe(200);
  await result.finished();
}
test("Órbita reflow equivalente a zoom de 200%", async ({page}) => {
  await page.setViewportSize({width:720,height:450});
  const session = await page.context().newCDPSession(page);
  await session.send("Emulation.setDeviceMetricsOverride", {width:720,height:450,deviceScaleFactor:2,mobile:false,screenWidth:1440,screenHeight:900});
  await openScreen(page, "/");
  await expect(page.getByRole("heading", {name:"O que você quer fazer hoje?"})).toBeVisible();
  await capture(page, "inicio-reflow-200pct");
  const reduced = await page.locator("body").evaluate(body => body.ownerDocument.defaultView!.matchMedia("(prefers-reduced-motion: reduce)").matches);
  expect(reduced).toBe(true);
  await page.keyboard.press("Tab");
  await expect(page.getByRole("link", {name:"Ir para o conteúdo"})).toBeFocused();
});
for(const viewport of [{name:"desktop",width:1440,height:900},{name:"tablet",width:768,height:1024},{name:"mobile",width:390,height:844}]){
  for(const screen of screens) test(`Órbita ${screen.name} ${viewport.name}`,async({page})=>{
    await page.setViewportSize(viewport);await openScreen(page,screen.path);
    await expect(page.getByRole("heading",{name:screen.heading,exact:true}).last()).toBeVisible();
    await capture(page,`${screen.name}-${viewport.name}`);
    const nav=page.getByTestId(viewport.name==="mobile"?"mobile-primary-navigation":"desktop-primary-navigation");
    await expect(nav.locator(":scope > *")).toHaveCount(5);
    if (viewport.name === "mobile") {
      const bounds = await nav.boundingBox();
      expect(bounds).not.toBeNull();
      expect(bounds!.x).toBeGreaterThanOrEqual(0);
      expect(bounds!.y + bounds!.height).toBeLessThanOrEqual(viewport.height + 1);
      for (const label of ["Início", "Carteira", "Mesa IA", "Mercado", "Planejar"]) await expect(nav.getByText(label, {exact:true})).toBeVisible();
    }
    const header = page.locator(".topbar");
    const title = await header.locator("h1").boundingBox();
    const account = await header.locator(".topbar-user").boundingBox();
    expect(title!.x + title!.width).toBeLessThanOrEqual(account!.x + 1);
    if(screen.name==="inicio"){
      await page.getByRole("heading",{name:"Composição da carteira"}).evaluate(element=>element.scrollIntoView({block:"start"}));
      await capture(page,`inicio-composicao-${viewport.name}`);
      await nav.getByRole("button",{name:"Mesa IA"}).click();
      await expect(page.getByRole("dialog",{name:"Mesa IA — pausada"})).toBeVisible();
      await capture(page,`mesa-ia-pausada-${viewport.name}`);await page.keyboard.press("Escape");
      await expect(nav.getByRole("button", {name:"Mesa IA",exact:true})).toBeFocused();
      await expect(page.getByRole("dialog", {name:"Mesa IA — pausada"})).toHaveCount(0);
      if (viewport.name === "mobile") {
        await page.locator("body").evaluate(body => body.ownerDocument.defaultView!.scrollTo(0, body.scrollHeight));
        const refresh = await page.getByRole("button", {name:"Atualizar cotações",exact:true}).boundingBox();
        const bar = await nav.boundingBox();
        expect(refresh!.y + refresh!.height).toBeLessThanOrEqual(bar!.y + 1);
      }
    }
    if(screen.name==="carteira"){
      await page.getByRole("heading",{name:"Posições",exact:true}).evaluate(element=>element.scrollIntoView({block:"start"}));await capture(page,`carteira-posicoes-${viewport.name}`);
      if(viewport.name==="mobile"){
        const wrappedValues=await page.locator(".position-card dd").evaluateAll(values=>values.filter(value=>{
          const range=value.ownerDocument.createRange();range.selectNodeContents(value);
          return range.getClientRects().length>1;
        }).map(value=>value.textContent));
        expect(wrappedValues,"Valores da fixture não devem quebrar os centavos").toEqual([]);
      }
    }
    if(screen.name==="configuracoes"){
      await page.getByRole("button",{name:"Sair da conta",exact:true}).click();await expect(page.getByLabel("Senha",{exact:true})).toBeVisible();await capture(page,`login-${viewport.name}`);
    }
  });
  test(`Órbita detalhes Planejar ${viewport.name}`,async({page})=>{
    await page.setViewportSize(viewport);await openScreen(page,"/planejar?secao=montar-carteira");
    await page.getByRole("button",{name:"Montar minha carteira"}).click();
    const card=page.locator(".recommended-asset").first();await expect(card).toContainText("PETR4");await card.scrollIntoViewIfNeeded();await capture(page,`planejar-cartoes-${viewport.name}`);
    await card.locator("details.asset-details > summary").click();await card.locator("details.indicator-provenance > summary").click();
    await card.locator(".indicator-table").scrollIntoViewIfNeeded();await capture(page,`planejar-detalhes-${viewport.name}`);
    await card.locator(".indicator-provenance").scrollIntoViewIfNeeded();await capture(page,`planejar-procedencia-${viewport.name}`);
  });
}
