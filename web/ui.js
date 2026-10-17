/* Responsive lobby and match controls. The physics engine owns the match state. */
(() => {
  'use strict';
  const game = window.WBA;
  if (!game.playable) { document.body.classList.add('director'); return; }
  const $ = id => document.getElementById(id);
  const menu = game.menu;
  const slots = ['a', 'b', 'c', 'd'];
  const pickKey = slot => `pick${slot.toUpperCase()}`;
  const slotName = slot => `fighter ${slots.indexOf(slot) + 1}`;
  const svg = name => `<svg class="icon" aria-hidden="true"><use href="#i-${name}"/></svg>`;
  const names = new Map(game.roster.map(w => [w.kind, w.name]));
  const imageCache = new Map();
  const categories = {
    blades: ['sword', 'katana', 'dagger', 'kunai', 'rapier', 'claws', 'dual_daggers', 'cleaver', 'scythe'],
    heavy: ['axe', 'hammer', 'warhammer', 'mace', 'flail', 'war_axe', 'tomahawk', 'halberd'],
    ranged: ['pistol', 'shuriken', 'boomerang'],
  };
  const descriptions = { katana: 'Critical strikes', rapier: 'Parry specialist', chainsaw: 'Contact damage', whip: 'Pulls opponents', pistol: 'Fires projectiles', shuriken: 'Spinning projectiles', boomerang: 'Returning projectiles' };
  let pickerSlot = 'a', filter = 'all', activeWorld = null, lastState = null, hudTime = 0, resultShown = false;
  let fighterRows = [], nextPending = false;
  const hintDesktop = document.querySelector('.desktop-hint').innerHTML;
  const hintTouch = document.querySelector('.touch-hint').textContent;

  function weaponImage(kind, color = '#d8e1cb') {
    const key = `${kind}:${color}`;
    if (imageCache.has(key)) return imageCache.get(key);
    const canvas = document.createElement('canvas');
    canvas.width = canvas.height = 180;
    const ctx = canvas.getContext('2d');
    if (!kind) {
      ctx.translate(90, 90); ctx.rotate(-.15);
      ctx.strokeStyle = color; ctx.lineWidth = 5; ctx.beginPath(); ctx.roundRect(-38, -38, 76, 76, 13); ctx.stroke();
      ctx.fillStyle = color;
      [[-20, -20], [20, -20], [0, 0], [-20, 20], [20, 20]].forEach(([x, y]) => { ctx.beginPath(); ctx.arc(x, y, 5, 0, Math.PI * 2); ctx.fill(); });
    } else {
      ctx.translate(90, 134); ctx.rotate(.34);
      const metal = ctx.createLinearGradient(-30, 0, 30, -120);
      metal.addColorStop(0, '#68765d'); metal.addColorStop(.35, color); metal.addColorStop(.52, '#ffffff'); metal.addColorStop(.68, color); metal.addColorStop(1, '#95a48a');
      ctx.fillStyle = metal; ctx.strokeStyle = metal; ctx.lineCap = 'round';
      game.drawBlade(kind, 65, 70, ctx);
    }
    const src = canvas.toDataURL(); imageCache.set(key, src); return src;
  }
  function announce(message) { $('announcement').textContent = message; }
  function syncSound() {
    document.querySelectorAll('.sound-toggle').forEach(button => {
      button.setAttribute('aria-label', game.muted ? 'Enable sound' : 'Mute sound');
      button.setAttribute('aria-pressed', String(game.muted));
      button.innerHTML = svg(game.muted ? 'muted' : 'sound');
    });
  }
  function syncLobby() {
    document.querySelectorAll('[name="mode"]').forEach(input => { input.checked = input.value === menu.mode; });
    document.querySelectorAll('[name="fighters"]').forEach(input => { input.checked = +input.value === menu.n; });
    for (const slot of slots) {
      const kind = menu[pickKey(slot)];
      const name = names.get(kind) || 'Random';
      $(`loadout-name-${slot}`).textContent = name;
      $(`loadout-${slot}`).src = weaponImage(kind, slot === 'a' ? '#d6edb4' : '#d6c3f5');
      $(`pick-${slot}`).hidden = slots.indexOf(slot) >= menu.n;
      if (slot === 'a' || slot === 'b') {
        $(`preview-name-${slot}`).textContent = name.toUpperCase();
        $(`preview-${slot}`).src = weaponImage(kind, slot === 'a' ? '#e6f8c6' : '#e3d3fa');
      }
      $(`pick-${slot}`).setAttribute('aria-label', `${slot === 'a' && menu.mode === 'play' ? 'Your weapon' : slotName(slot)}: ${name}. Change weapon`);
    }
    $('slot-a-label').textContent = menu.mode === 'play' ? 'YOUR WEAPON' : 'FIGHTER 1';
    $('slot-b-label').textContent = menu.mode === 'play' ? 'OPPONENT' : 'FIGHTER 2';
    $('preview-role-a').textContent = menu.mode === 'play' ? 'YOU' : 'AI';
    $('preview-extra').hidden = menu.n === 2;
    $('preview-extra').textContent = slots.slice(2, menu.n).map(slot => names.get(menu[pickKey(slot)]) || 'Random').join(' + ');
    $('extra-fighters-note').hidden = menu.n === 2;
    $('start-match').querySelector('span').textContent = menu.mode === 'play' ? 'Enter the arena' : 'Watch the battle';
    $('match-summary').textContent = `${menu.n} fighters · ${menu.mode === 'play' ? 'You take control' : 'All fighters on autopilot'} · Last one standing wins`;
    game.save();
  }
  function openDialog(dialog) {
    if (dialog.open) return;
    dialog.dataset.resume = String(game.world.state !== 'menu' && game.world.state !== 'over' && !game.paused);
    if (dialog.dataset.resume === 'true') game.pause(true);
    dialog.showModal();
  }
  function resumeAfterDialog(dialog) {
    if (dialog.open) return;
    const shouldResume = dialog.dataset.resume === 'true';
    dialog.dataset.resume = 'false';
    if (shouldResume) { game.pause(false); $('c').focus({ preventScroll: true }); }
  }
  function closeDialog(dialog) {
    if (!dialog.open) return;
    dialog.close();
    // The native close event is queued; restore controls before the next key.
    resumeAfterDialog(dialog);
  }
  document.querySelectorAll('dialog').forEach(dialog => {
    dialog.addEventListener('keydown', event => {
      if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); closeDialog(dialog); }
    });
    dialog.querySelectorAll('[data-close]').forEach(button => button.addEventListener('click', () => closeDialog(dialog)));
    dialog.addEventListener('close', () => resumeAfterDialog(dialog));
    dialog.addEventListener('click', event => {
      const rect = dialog.getBoundingClientRect();
      if (event.target === dialog && (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom)) closeDialog(dialog);
    });
  });
  function weaponCategory(kind) { return Object.keys(categories).find(key => categories[key].includes(kind)) || 'other'; }
  function buildWeaponGrid() {
    const query = $('weapon-search').value.trim().toLowerCase();
    const selected = menu[pickKey(pickerSlot)];
    const items = [{ kind: null, name: 'Random', reach: 1 }, ...game.roster].filter(w => (!query || w.name.toLowerCase().includes(query)) && (filter === 'all' || (w.kind && weaponCategory(w.kind) === filter)));
    $('weapon-grid').replaceChildren();
    for (const weapon of items) {
      const button = document.createElement('button');
      button.className = 'weapon-tile'; button.dataset.weapon = weapon.kind || 'random';
      button.setAttribute('aria-pressed', String(selected === weapon.kind));
      const detail = !weapon.kind ? 'Let fate decide' : descriptions[weapon.kind] || (weapon.reach >= 1.15 ? 'Long reach' : weapon.reach < .85 ? 'Close quarters' : 'Melee fighter');
      button.innerHTML = `<img src="${weaponImage(weapon.kind)}" alt=""><strong>${weapon.name}</strong><small>${detail}</small><svg class="icon selection-check" aria-hidden="true"><use href="#i-check"/></svg>`;
      button.addEventListener('click', () => {
        menu[pickKey(pickerSlot)] = weapon.kind;
        syncLobby();
        announce(`${weapon.name} selected for ${slotName(pickerSlot)}.`);
        closeDialog($('weapon-dialog'));
      });
      $('weapon-grid').append(button);
    }
    $('no-weapons').hidden = items.length > 0;
    const count = items.filter(w => w.kind).length;
    $('weapon-count').textContent = `${count} weapon${count === 1 ? '' : 's'}${items.some(w => !w.kind) ? ' + random' : ''}`;
  }
  function openWeapons(slot) {
    pickerSlot = slot; filter = 'all'; $('weapon-search').value = '';
    $('weapon-dialog-title').textContent = slot === 'a' && menu.mode === 'play' ? 'Choose your weapon.' : `Equip ${slotName(slot)}.`;
    $('picker-note').textContent = `Choose a weapon for ${slot === 'a' && menu.mode === 'play' ? 'your fighter' : slotName(slot)}. It will be equipped for your next match.`;
    document.querySelectorAll('[data-filter]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.filter === filter)));
    buildWeaponGrid(); openDialog($('weapon-dialog')); $('weapon-search').focus();
  }
  function start() {
    if (game.world.state !== 'menu' || document.querySelector('dialog[open]')) return;
    game.save(); game.start(); $('c').focus({ preventScroll: true }); window.scrollTo(0, 0);
  }
  function home() {
    document.querySelectorAll('dialog[open]').forEach(dialog => { dialog.dataset.resume = 'false'; dialog.close(); });
    game.home(); activeWorld = null; lastState = null;
    update(game.world); syncLobby(); $('start-match').focus({ preventScroll: true }); window.scrollTo(0, 0);
  }
  function pause(automatic = false) {
    if (!['intro', 'fight'].includes(game.world.state) || document.querySelector('dialog[open]')) return;
    if (game.paused && automatic) return;
    game.pause(true); $('pause-dialog').dataset.resume = 'true'; $('pause-dialog').showModal(); $('resume-match').focus();
  }
  function rematch() {
    if (nextPending || game.world.state !== 'over') return;
    nextPending = true; $('rematch').disabled = true;
    $('rematch').textContent = 'Preparing match…';
    game.next(() => {
      nextPending = false; $('rematch').disabled = false;
      $('rematch').innerHTML = `Fight again ${svg('arrow')}`;
      $('c').focus({ preventScroll: true });
    });
  }
  function buildHud(world) {
    fighterRows = []; $('fighters-hud').replaceChildren();
    world.fighters.forEach(fighter => {
      const card = document.createElement('div');
      card.className = `fighter-card${fighter.idx === world.playerIdx ? ' player' : ''}`;
      card.style.setProperty('--fighter-color', fighter.tint);
      card.innerHTML = `<div class="fighter-card-top"><img src="${weaponImage(fighter.kind, fighter.tint)}" alt=""><div><strong>${fighter.name}</strong><small>${fighter.idx === world.playerIdx ? 'YOU' : 'AI FIGHTER'}${fighter._role ? ' · ' + fighter._role : ''}</small></div><span class="hp-value"></span></div><div class="hp-track" role="progressbar" aria-label="${fighter.name} health" aria-valuemin="0" aria-valuemax="${Math.ceil(fighter.maxHp)}"><div class="hp-fill"></div></div><div class="fighter-buff"></div>`;
      $('fighters-hud').append(card);
      fighterRows.push({ card, value: card.querySelector('.hp-value'), track: card.querySelector('.hp-track'), fill: card.querySelector('.hp-fill'), buff: card.querySelector('.fighter-buff') });
    });
    $('arena-name').textContent = world.theme.name;
    $('match-mode').textContent = world.playerIdx < 0 ? 'SPECTATOR MODE / ALL AI' : 'QUICK PLAY / YOU VS AI';
    $('contender-count').textContent = String(world.n).padStart(2, '0');
    $('rule-name').textContent = world.mutator ? world.mutator.name : 'Last one standing';
    $('rule-description').textContent = world.mutator ? world.mutator.blurb : 'The arena closes in as you battle. Stay alive and protect your HP.';
    const hazards = { pit: 'Watch the center: the lava pit deals damage.', pegs: 'Bumpers change your trajectory. Use the ricochet.', saw: 'Keep clear of the moving saw blade.', wind: 'Crosswinds push every fighter off course.', ice: 'Slippery floor. Plan your next move early.' };
    $('hazard-description').textContent = hazards[world.hazard] || 'Look for glowing pickups to turn the fight around.';
    document.querySelector('.desktop-hint').innerHTML = world.playerIdx < 0 ? 'Sit back. Every fighter is controlled by AI.' : hintDesktop;
    document.querySelector('.touch-hint').textContent = world.playerIdx < 0 ? 'Spectating · Every fighter is controlled by AI.' : hintTouch;
    $('c').setAttribute('aria-label', world.playerIdx < 0 ? 'Spectating the AI battle. Use the Pause button to pause.' : 'Weapon Ball arena. Move with WASD or arrow keys, or aim and hold your pointer to thrust.');
    resultShown = false; $('result-overlay').hidden = true; $('fund').hidden = true;
  }
  function update(world) {
    const inMenu = world.state === 'menu';
    if (lastState !== world.state) {
      $('lobby').hidden = !inMenu; $('match').hidden = inMenu;
      document.body.classList.toggle('playing', !inMenu);
      $('pause-match').disabled = world.state === 'over';
      $('battle-phase').innerHTML = `<i class="status-dot"></i> ${world.state === 'intro' ? 'GET READY' : world.state === 'fight' ? 'BATTLE IN PROGRESS' : 'MATCH COMPLETE'}`;
      if (!inMenu) announce(world.state === 'fight' ? 'Fight! Last one standing wins.' : world.state === 'intro' ? 'Your match is starting.' : world.finishReason === 'double_ko' ? 'Double KO. No survivors.' : `${world.winner?.name || 'A fighter'} wins the match.`);
      lastState = world.state;
    }
    if (inMenu) return;
    if (activeWorld !== world) { buildHud(world); activeWorld = world; hudTime = 0; }
    $('countdown').hidden = world.state !== 'intro';
    if (world.state === 'intro') {
      const label = game.countdown(world.t);
      if ($('countdown').dataset.label !== label) { $('countdown').dataset.label = label; $('countdown').innerHTML = `${label}<small>${world.playerIdx < 0 ? 'LET THE CHAOS BEGIN' : 'GET YOUR WEAPON READY'}</small>`; }
    }
    if (world.state === 'over' && world.t > .7 && !resultShown && world.winner) {
      resultShown = true;
      const win = world.winner, draw = world.finishReason === 'double_ko', playerWon = !draw && win.idx === world.playerIdx;
      $('result-title').textContent = draw ? 'Double knockout.' : playerWon ? 'You own the arena.' : `${win.name} wins.`;
      $('result-eyebrow').textContent = draw ? 'NO SURVIVORS / RUN IT BACK' : world.finishReason === 'timeout' ? 'TIME UP / HIGHEST HP WINS' : playerWon ? 'VICTORY / LAST ONE STANDING' : world.playerIdx < 0 ? 'LAST ONE STANDING' : 'GOOD FIGHT. GO AGAIN.';
      $('result-stats').textContent = draw ? `Both went down in ${world.duration.toFixed(1)} seconds.` : `${Math.max(0, Math.ceil(win.hp))} HP · ${Math.round(win.damageDealt)} damage · ${win.kills} KO${win.kills === 1 ? '' : 's'} · ${world.duration.toFixed(1)}s`;
      $('result-overlay').hidden = false; $('fund').hidden = false;
      if (!document.querySelector('dialog[open]')) $('rematch').focus({ preventScroll: true });
    }
    if (performance.now() - hudTime < 100) return;
    hudTime = performance.now();
    const seconds = world.state === 'intro' ? game.maxSeconds : world.state === 'over' ? 0 : Math.max(0, Math.ceil(game.maxSeconds - world.t));
    $('battle-clock').textContent = `0:${String(seconds).padStart(2, '0')}`;
    $('battle-clock').classList.toggle('urgent', world.state === 'fight' && seconds <= 6);
    $('alive-count').textContent = `${world.fighters.filter(f => f.alive).length} / ${world.n} ALIVE`;
    world.fighters.forEach((fighter, i) => {
      const row = fighterRows[i], hp = Math.max(0, Math.ceil(fighter.hp));
      row.value.textContent = fighter.alive ? `${hp} HP` : 'OUT';
      row.track.setAttribute('aria-valuenow', String(hp));
      row.fill.style.width = `${Math.max(0, Math.min(100, fighter.hp / fighter.maxHp * 100))}%`;
      row.card.classList.toggle('out', !fighter.alive); row.card.classList.toggle('low', fighter.alive && fighter.hp < fighter.maxHp * .25);
      row.buff.textContent = fighter.buff && fighter.alive ? `${fighter.buff.name || fighter.buff.id.toUpperCase()} · ${Math.ceil(fighter.buff.t)}s` : fighter.kills ? `${fighter.kills} KO${fighter.kills === 1 ? '' : 's'}` : ' ';
    });
  }

  document.querySelectorAll('[name="mode"]').forEach(input => input.addEventListener('change', () => { menu.mode = input.value; syncLobby(); }));
  document.querySelectorAll('[name="fighters"]').forEach(input => input.addEventListener('change', () => { menu.n = +input.value; syncLobby(); }));
  $('randomize').addEventListener('click', () => { slots.forEach(slot => { menu[pickKey(slot)] = null; }); syncLobby(); announce('All weapons set to random.'); });
  slots.forEach(slot => $(`pick-${slot}`).addEventListener('click', () => openWeapons(slot)));
  $('arsenal-nav').addEventListener('click', () => openWeapons('a'));
  $('arena-nav').addEventListener('click', () => game.world.state === 'menu' ? $('start-match').focus() : pause());
  document.querySelector('.brand').addEventListener('click', event => { event.preventDefault(); if (game.world.state === 'menu' || game.world.state === 'over') home(); else pause(); });
  document.querySelectorAll('[data-help]').forEach(button => button.addEventListener('click', () => openDialog($('help-dialog'))));
  document.querySelectorAll('.sound-toggle').forEach(button => button.addEventListener('click', () => action('mute')));
  $('weapon-search').addEventListener('input', buildWeaponGrid);
  document.querySelectorAll('[data-filter]').forEach(button => button.addEventListener('click', () => {
    filter = button.dataset.filter;
    document.querySelectorAll('[data-filter]').forEach(item => item.setAttribute('aria-pressed', String(item === button)));
    buildWeaponGrid();
  }));
  $('start-match').addEventListener('click', start);
  $('pause-match').addEventListener('click', () => pause());
  $('leave-match').addEventListener('click', () => game.world.state === 'over' ? home() : pause());
  $('resume-match').addEventListener('click', () => closeDialog($('pause-dialog')));
  $('pause-lobby').addEventListener('click', home);
  $('result-lobby').addEventListener('click', home);
  $('rematch').addEventListener('click', rematch);
  function action(name) {
    if (name === 'mute') { game.mute(); game.save(); syncSound(); announce(game.muted ? 'Sound muted.' : 'Sound enabled.'); }
    else if (name === 'start') start();
    else if (name === 'pause' || name === 'autopause') pause(name === 'autopause');
    else if (name === 'rematch') rematch();
  }
  window.WBA_UI_ACTION = action; window.WBA_UI_UPDATE = update;
  syncLobby(); syncSound(); update(game.world);
})();
