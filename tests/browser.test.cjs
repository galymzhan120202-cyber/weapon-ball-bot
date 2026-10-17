const { test, before, after } = require('node:test');
const assert = require('node:assert/strict');
const { chromium } = require('playwright');
const http = require('node:http');
const fs = require('node:fs/promises');
const path = require('node:path');
let browser, server, base;
before(async () => {
  const root = path.resolve(__dirname, '..');
  server = http.createServer(async (request, response) => {
    const pathname = new URL(request.url, 'http://localhost').pathname;
    const relative = pathname === '/' ? 'index.html' : pathname.slice(1);
    if (!/^(index\.html|web\/[\w.-]+|fonts\/[\w.-]+)$/.test(relative)) { response.writeHead(404).end(); return; }
    try {
      const content = await fs.readFile(path.join(root, relative));
      const mime = {'.html':'text/html','.js':'text/javascript','.css':'text/css','.svg':'image/svg+xml','.ttf':'font/ttf'}[path.extname(relative)];
      response.writeHead(200, {'Content-Type':mime || 'application/octet-stream'}).end(content);
    } catch { response.writeHead(404).end(); }
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  base = `http://127.0.0.1:${server.address().port}/`;
  browser = await chromium.launch({headless:true, ...(process.env.WBA_BROWSER ? {executablePath:process.env.WBA_BROWSER} : {})});
});
after(async () => { await browser?.close(); await new Promise(resolve => server?.close(resolve)); });
async function open(query = '', options = {}) {
  const page = await browser.newPage({viewport:{width:1440,height:1000}, ...options});
  page.errors = []; page.on('pageerror', error => page.errors.push(error.message));
  await page.goto(base + '?ads=0&mute=1&' + query);
  await page.waitForFunction(() => !!window.WBA_UI_UPDATE || document.body.classList.contains('director'));
  return page;
}

test('lobby, search, opponent slots, persistence, mute and pause work without reloads', async () => {
  const page = await open('mut=0&hz=0');
  await page.click('#randomize');
  await page.click('#pick-b');
  await page.fill('#weapon-search', 'Katana');
  await page.click('[data-weapon="katana"]');
  await page.locator('[name="fighters"][value="4"]').check();
  await page.click('#start-match');
  assert.deepEqual(await page.evaluate(() => ({n:WBA.world.n, opponent:WBA.world.fighters[1].kind, player:WBA.world.playerIdx})), {n:4,opponent:'katana',player:0});
  assert.notEqual(await page.evaluate(() => WBA.world.fighters[0].kind), 'katana');
  await page.click('#pause-match');
  const pausedAt = await page.evaluate(() => WBA.world.t);
  await page.waitForTimeout(180);
  assert.equal(await page.evaluate(() => WBA.world.t), pausedAt);
  await page.click('#resume-match');
  await page.keyboard.press('m');
  assert.equal(await page.evaluate(() => WBA.muted), false);
  assert.equal(await page.evaluate(() => WBA.world.n), 4);
  await page.keyboard.press('Escape');
  await page.click('#pause-lobby');
  await page.reload();
  assert.deepEqual(await page.evaluate(() => ({n:WBA.menu.n,a:WBA.menu.pickA,b:WBA.menu.pickB})), {n:4,a:null,b:'katana'});
  assert.deepEqual(page.errors, []); await page.close();
});

test('keyboard dialogs, filtering and empty results remain usable', async () => {
  const page = await open();
  await page.click('#arsenal-nav');
  assert.equal(await page.locator('.weapon-tile').count(),27);
  await page.click('[data-filter="ranged"]');
  assert.equal(await page.locator('.weapon-tile').count(),3);
  await page.fill('#weapon-search','no such weapon');
  assert.equal(await page.locator('#no-weapons').isVisible(),true);
  await page.keyboard.press('Escape');
  assert.equal(await page.locator('#weapon-dialog').isVisible(),false);
  assert.equal(await page.evaluate(() => document.activeElement.id),'arsenal-nav');
  await page.locator('.main-nav [data-help]').click();
  await page.keyboard.press('Escape');
  assert.deepEqual(page.errors, []); await page.close();
});

test('shared four-fighter loadouts preserve every slot and allow individual changes', async () => {
  const page = await open('weapons=sword,axe,rapier,whip&mut=0&hz=0');
  assert.equal(await page.locator('#pick-d').isVisible(),true);
  assert.equal(await page.locator('#loadout-name-c').textContent(),'Rapier');
  await page.click('#pick-d');
  await page.fill('#weapon-search','pistol');
  await page.click('[data-weapon="pistol"]');
  await page.click('#start-match');
  assert.deepEqual(await page.evaluate(() => WBA.world.fighters.map(f=>f.kind)),['sword','axe','rapier','pistol']);
  await page.click('#pause-match');
  await page.click('#pause-lobby');
  await page.click('#randomize');
  assert.deepEqual(await page.evaluate(() => ['pickA','pickB','pickC','pickD'].map(key=>WBA.menu[key])),[null,null,null,null]);
  assert.deepEqual(page.errors,[]);await page.close();
});

test('responsive touch layouts fit at 320px, 390px, tablet and desktop', async () => {
  const page = await open('', {hasTouch:true, isMobile:true});
  for (const width of [320,390,768,1440]) {
    await page.setViewportSize({width,height:900});
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),true,`overflow at ${width}px`);
    await page.click('#pick-a');
    assert.equal(await page.evaluate(() => {const d=document.querySelector('dialog[open]');return d.scrollWidth<=d.clientWidth;}),true);
    await page.keyboard.press('Escape');
  }
  await page.setViewportSize({width:390,height:844});
  await page.click('#start-match');
  assert.equal(await page.locator('.touch-hint').isVisible(),true);
  const bounds = await page.locator('#c').boundingBox();
  assert.ok(Math.abs(bounds.width-bounds.height)<1);
  await page.touchscreen.tap(bounds.x+bounds.width/2,bounds.y+bounds.height/2);
  await page.dispatchEvent('#c','pointercancel',{pointerId:1});
  assert.equal(await page.evaluate(() => input.thrust),false);
  assert.deepEqual(page.errors, []);
  await page.close();
});

test('coincident fighters separate, dead fighters cannot attack, and fast projectiles hit once', async () => {
  const page = await open('auto=1&drive=ext&seed=8&weapons=sword,axe&mut=0&hz=0&pickups=0');
  const result = await page.evaluate(() => {
    const w = WBA.world, [a,b] = w.fighters;
    w.state='fight';w.t=5;a.x=b.x=540;a.y=b.y=1000;a.vx=a.vy=b.vx=b.vy=0;
    w._collide(a,b,1/120);
    const separated=Math.hypot(a.x-b.x,a.y-b.y)>a._baseR+b._baseR-.01;
    a.alive=false; a.x=b.x; a.y=b.y;const hp=b.hp;w.pairCd.clear();w._collide(a,b,1/120);
    const noGhost=b.hp===hp;
    a.alive=true;a.hp=b.hp=100;a.x=200;b.x=600;a.y=b.y=1000;b.shield=0;
    w.projectiles=[{x:400,y:1000,vx:30000,vy:0,dmg:10,col:'#fff',spin:0,rot:0,owner:a,returns:false,life:0,back:false,kind:'pistol'}];
    w._stepWeapons(1/60);
    return {separated,noGhost,projectiles:w.projectiles.length,hp:b.hp,damage:a.damageDealt};
  });
  assert.ok(result.separated);assert.ok(result.noGhost);assert.equal(result.projectiles,0);assert.ok(result.hp<100);assert.ok(result.damage>=10);
  assert.deepEqual(page.errors,[]);await page.close();
});

test('director is deterministic and extra rendered frames do not alter physics', async () => {
  const page = await open('auto=1&drive=ext&seed=42&n=4');
  async function simulate(extra) {
    return page.evaluate(extra => {
      let frames=0;
      while(!window.__WBA_DONE__ && frames++<2600) {__WBA_TICK__();if(extra)render(WBA.world);}
      return {state:__WBA_STATE__(),meta:__WBA_META__(),audio:__WBA_AUDIO_LOG__(),canvas:[document.querySelector('#c').width,document.querySelector('#c').height]};
    },extra);
  }
  const first=await simulate(false);
  assert.equal(first.state.done,true);assert.deepEqual(first.canvas,[1080,1920]);
  assert.equal(await page.locator('.site-header').isVisible(),false);
  await page.reload();const second=await simulate(true);
  assert.deepEqual(second,first);
  assert.deepEqual(page.errors,[]);await page.close();
});

test('watch mode finishes, reports a winner and rematches with the same loadout', async () => {
  const page = await open('mut=instakill&hz=0&pickups=0');
  await page.locator('[name="mode"][value="watch"]').check();
  await page.click('#start-match');
  assert.equal(await page.evaluate(() => WBA.world.playerIdx),-1);
  // Drive the real simulation through its supported recorder clock to avoid wall-clock waits.
  await page.evaluate(() => {for(let i=0;i<2600&&WBA.world.state!=='over';i++)__WBA_TICK__();for(let i=0;i<70;i++)__WBA_TICK__();WBA_UI_UPDATE(WBA.world);});
  assert.equal(await page.locator('#result-overlay').isVisible(),true);
  const chosen=await page.evaluate(()=>WBA.world.fighters.map(f=>f.kind));
  await page.click('#rematch');
  assert.equal(await page.evaluate(()=>WBA.world.state),'intro');
  assert.deepEqual(await page.evaluate(()=>WBA.world.fighters.map(f=>f.kind)),chosen);
  assert.deepEqual(page.errors,[]);await page.close();
});

test('a simultaneous knockout reports a draw instead of a false victory', async () => {
  const page = await open('mut=0&hz=0');
  await page.click('#start-match');
  await page.evaluate(() => {
    const w=WBA.world;
    for(const fighter of w.fighters){fighter.hp=0;fighter.alive=false;}
    w.winner=w.fighters[0];w.finishReason='double_ko';w.duration=12.5;w.state='over';w.t=1;
    WBA_UI_UPDATE(w);
  });
  assert.equal(await page.locator('#result-title').textContent(),'Double knockout.');
  assert.match(await page.locator('#result-eyebrow').textContent(),/NO SURVIVORS/);
  assert.deepEqual(page.errors,[]);await page.close();
});
