# Weapon Ball Bot — Setup нұсқаулығы

Код пен pipeline толық дайын (`battle_sim.py`, `video_gen.py`, `scheduler.py`,
`.github/workflows/upload.yml`). Бұл бот қалған 5 ботпен (`ai-tech-shorts-bot`,
`music-shorts-bot`, `lofi-jazz-radio-bot`, `movie-facts-bot`) **бірдей upload/cron
архитектурада**, бірақ мазмұны түбегейлі бөлек:

**Gemini/LLM де, дауыс (TTS) та, Pexels/stock footage те жоқ.** Екі қару-иконка
(`pymunk` физикасымен) қорапта соғысады, HP есептегіш азаяды, жеңімпаз шыққанда
видео аяқталады. Фон, HP-бар, flash, жарыс — бәрі кодпен генерацияланады
(`battle_sim.py`), соққы дыбыстары (`clang`) numpy-мен синтезделеді — нақты дыбыс
файлы да жүктелмейді. Тек фон музыка сырттан алынады (Openverse/YouTube).

## 1. Жаңа YouTube арна

1. Жаңа Google аккаунт ашыңыз (немесе қазіргі аккаунтта Brand Account құрыңыз).
2. YouTube Studio-да арнаны weapon-fight/battle-simulator нишасына сай атаумен,
   суретпен баптаңыз (мыс. "Weapon Ball Arena").

## 2. Google Cloud OAuth (жүктеу үшін міндетті)

1. https://console.cloud.google.com — жаңа жоба жасаңыз (мыс. `WeaponBallBot`).
2. **YouTube Data API v3**-ті қосыңыз (APIs & Services → Library).
3. **OAuth consent screen** баптаңыз (External). Бірден **"In production"**
   күйіне ауыстырыңыз (Testing емес) — Testing статусында refresh token 7
   күннен кейін мерзімі бітеді де, upload үзіліп қалады.
4. **Credentials → Create Credentials → OAuth client ID → Desktop app** жасап,
   JSON жүктеп алыңыз → `client_secrets.json` деп осы папкаға салыңыз.
5. Жергілікті бір рет `python video_gen.py` іске қосыңыз — браузерде жаңа
   арнамен логин болып, `youtube_token.json` автоматты жасалады.

**Маңызды:** OAuth логин кезінде дәл жаңа Weapon Ball арнаға тиесілі Google
аккаунтпен кіріңіз.

## 3. GitHub repo + Secrets

1. Жаңа бөлек GitHub repo ашыңыз (мыс. `weapon-ball-bot`), осы папканы push етіңіз.
2. Repo → Settings → Secrets and variables → Actions → төмендегі 4 Secret қосыңыз:
   - `WBALL_TELEGRAM_NOTIFY_TOKEN`
   - `WBALL_TELEGRAM_NOTIFY_CHAT_ID`
   - `WBALL_CLIENT_SECRETS_JSON` — `client_secrets.json` файлының толық мазмұны
   - `WBALL_YOUTUBE_TOKEN_JSON` — `youtube_token.json` файлының толық мазмұны

   Telegram-ды басқа боттарыңызбен ортақ пайдалануға болады (cron уақыттары
   15 мин ығыстырылған, соқтықпайды).

## 4. Музыка (Openverse API — автоматты, кілтсіз)

`ai-tech-shorts-bot`/`movie-facts-bot`-пен бірдей: [Openverse API](https://api.openverse.org/)
арқылы CC0/CC-BY лицензиялы **action/electronic/energetic** фон музыка автоматты
жүктеледі, кілт керек емес. CC-BY трек түскенде атрибуция видео сипаттамасына
автоматты қосылады.

**Сақтық fallback:** `music/` папкасында 3 royalty-free трек бар (AITechShorts-тан
көшірілген, `fallback_attribution.json`-мен бірге) — Openverse/желі сирек сәтсіз
болған жағдайға.

## 5. Қару-иконка, арена, физика және "juice" — API/кілт керек емес

Ешбір баптау қажет емес. `battle_sim.py`:
- **26 қару түрінен** (Sword, Katana, Axe, Hammer, Warhammer, Spear, Trident,
  Dagger, Kunai, Mace, Flail, Nunchaku, Whip, Scythe, Claws, Chainsaw, Staff,
  Shuriken, Rapier, Halberd, Cleaver, Boomerang, Pistol, Dual Daggers, War Axe,
  Tomahawk) кездейсоқ **2, 3 немесе 4-уін**
  таңдайды (салмақталған: 55% — 1v1 дуэль, 28% — 3-жақты, 17% — 4-жақты
  "battle royale"), әрқайсысын PIL-мен геометриялық фигура + бағытты
  жарық→қараңғы градиент ретінде салады (нақты сурет/фото жоқ — Content ID
  claim мүлдем болмайды, басқа ойындардың арт-активтері көшірілмейді, тек
  концепция-алуан түрлілігінен шабыттанған original дизайн);
- **16 арена-тақырыбынан** (Midnight Arena, Neon City, Lava Pit, Ice Cave,
  Cyber Grid, Deep Space, Toxic Lab, Sunset Coliseum, Volcanic Forge, Frozen
  Peak, Golden Temple, Storm Clouds, Blood Moon, Coral Reef, Desert Dunes,
  Radioactive Waste) біреуін кездейсоқ таңдайды — градиент түсі, тор түсі,
  қалқымалы бөлшектер бәрі тақырыпқа сай өзгереді, сондықтан күнделікті
  видеолар бір-біріне ұқсамайды;
- `pymunk`-пен эластикалық физика симуляциясын жүргізеді (арнайы "lunge" импульс
  әр қаруды кездейсоқ бір қарсыласына мезгіл сайын жақындатып, шайқасты
  белсенді ұстайды — 3-4 қаруда бөлек топтарға бөлініп кетуден сақтайды);
- әр соққыда HP азайтады (қару "power" статистикасына қарай асимметриялы),
  HP 0-ге жеткен қару "OUT!" баннерімен экраннан жоғалады (`space.remove`);
- тірі қалған біреу болғанда немесе `BATTLE_MAX_SECONDS` толғанда (ең көп
  HP қалғанмен / соңғы жойылғанмен tie-break) жеңімпазды жариялайды.
- **"3-2-1-FIGHT!"** intro countdown, қозғалыс ізі (motion trail), соққыда
  экран дірілі + urон саны popup + spark burst, KO кезінде flash+банер,
  фон музыка соққыда қысқа "duck" болады — бәрі кодпен, дайын аудио/видео
  файл жоқ.

Толығымен детерминистикалық: бір `seed`-пен бірдей нәтиже қайталанады (жергілікті
тексеру/debug үшін пайдалы), бірақ әр жүктеу кездейсоқ жаңа `seed` алады —
2 қарудың C(26,2)=325 + 3 қарудың C(26,3)=2600 + 4 қарудың C(26,4)=14950
комбинациясы × 16 арена = **286 000+ бірегей видео нұсқасы**.

**Pistol** басқаларынан бөлек — жалғыз атыс қаруы: қалыпты соғысу физикасына
қатысумен қатар, кездейсоқ тірі қарсыласқа мезгіл сайын (~1.4-2.0 сек)
оқ атады (жеке collision subsystem, muzzle flash + оқ ұшуы + соққы ұшқыны +
дыбыс). Баланс есебі `analyze_balance.py` арқылы қайталанады: әр қаруға
бірдей матч саны беріледі. Ескі нұсқалардың жеңіс пайызы жаңа физикаға
дәлел ретінде қолданылмайды.

## 6. Монетизация туралы маңызды ескерту

- Физика/визуал және SFX кодпен жасалады. Сыртқы музыканың лицензиясы мен
  attribution мәліметін әр трек үшін сақтаңыз; авторлық құқық шағымының
  болмауына кепілдік берілмейді.
- Монетизацияның өзекті талаптары мен арнаның жағдайын YouTube Studio-дағы
  Earn бөлімінен қараңыз. Бот қаралымға немесе монетизацияға кепіл бермейді.

## 7. Болашақ жоспар: контенттен ойынға

Бұл бот екі мақсатқа қызмет етеді:
1. **Қазір:** YouTube Shorts арқылы форматтың "жанасатынын" (views/аудитория)
   тегін тексеру.
2. **Кейін:** формат дәлелденсе, `battle_sim.py`-дегі қару тізімі
   (`WEAPON_POOL`), урон формуласы, physics-ережелері нақты интерактивті
   мобильді ойынның **дизайн-негізі** ретінде пайдаланылады. Python/pymunk
   App Store-ге тікелей шықпайды — сол кезде Unity немесе Godot-та қайта
   жазылады, бірақ бұл жерде тексерілген механика тікелей көшіріледі (бекер
   жұмыс болмайды).

## 8. Тексеру реті

1. `.env.example`-ды `.env` етіп көшіріп, нақты кілттермен толтырыңыз.
2. `ffmpeg`-тің жергілікті компьютерде орнатылғанын тексеріңіз (`ffmpeg -version`).
3. `pip install -r requirements.txt`
4. Жергілікті сынау (жүктеместен): `python -c "from video_gen import generate_video; generate_video(skip_upload=True)"`
5. `final_shorts.mp4`-ты тексеріңіз (физика/HP/дыбыс/жеңімпаз баннері дұрыс па).
6. Нақты жүктеуді бір рет қолмен сынаңыз: `python video_gen.py`
7. Барлығы жұмыс істесе, GitHub Actions-та `workflow_dispatch` арқылы бір рет
   қолмен іске қосып тексеріңіз.
8. Содан кейін ғана cron кестесіне сеніп қалдырыңыз.

## 9. Ойын интерфейсі және жоба құрылымы

- `index.html` — бейімделетін мәзір, іздеуі бар қару каталогы, нұсқаулық,
  матч нәтижесі және пауза терезелері.
- `web/styles.css` — компьютер/телефонға арналған дизайн; пернетақта фокусы,
  сенсорлық басқару және reduced-motion баптауы ескерілген.
- `web/ui.js` — Play/Watch, 2–4 ойыншы, қару таңдауы, HP, дыбыс, пауза,
  қайта ойнау. Таңдаулар браузерде сақталады.
- `web/game.js` — 120 Hz браузер физикасы. Ойынға шаршы көрініс беріледі;
  `?auto=1&drive=ext&seed=42` жазу режимінде 1080×1920 кадр және
  `__WBA_TICK__`, `__WBA_META__`, `__WBA_AUDIO_LOG__` интерфейстері сақталған.
- `battle_sim.py` — Python/Pymunk симуляциясы, PIL кадрлары, синтезделген SFX.
- `battle_director.py` — бірнеше шынайы симуляцияны салыстырып, қарқыны жақсысын
  таңдайды; HP не жеңімпазды жасанды өзгертпейді.
- `video_gen.py` — музыка, метадеректер, рендер, YouTube жүктеуі;
  `scheduler.py` және `upload.yml` — бұрынғы жариялау кестесі.

Басқару: pointer/touch арқылы бағыттап, ұстап тұрып қозғалу; WASD/бағыт
пернелері; `Esc`/`P` — пауза; `M` — дыбыс. Терезеден кеткенде матч паузаға
түседі. Матч біткенде қайта ойнау не қаруды өзгертуге болады.

Жергілікті ашу: `index.html` файлын браузерде ашыңыз. GitHub Pages workflow
`index.html`, `web/` және `fonts/` файлдарын бірге жариялайды.

## 10. Shorts іріктеуі және тексерілетін сапа

`BATTLE_CANDIDATES=6` бір видео алдында алты ықтимал шайқасты есептейді
(1–24 аралығында). Баға алғашқы соққы уақытын, соққылар арасындағы ең ұзақ
үзілісті, ұзақтығын, басымдық ауысуын және финал түрін ескереді.
Соңғы видеоларда қайталанбаған матчапқа басымдық беріледі.

`BATTLE_MIN_SECONDS=8` — іріктеу мақсаты. Жеңімпаз ерте анықталса, видео оны
күтіп созылмайды. KO кезінде барлық физикалық бөлшектер жойылады; бір
жанасуда бірнеше hitbox уронды қабаттап есептемейді. Физика рендер FPS-іне
тәуелсіз. Replay арена көлемін сақтап, финал нақты соңғы күйді көрсетеді.

Бастапқы 0,9 секундта нақты шайқастың қозғалыстағы үзіндісі және «PICK YOUR
WINNER» мәтіні бар. Жеңімпаз сипаттамада алдын ала ашылмайды. Сипаттамада
сол қарулармен браузерде ойнау сілтемесі болады.

Әр рендер `battle_manifest.json` жасайды: seed, матчап, нақты winner
(double KO болса `null`), кандидаттардың бағасы және физика диагностикасы.
GitHub Actions бұл есепті 30 күн сақтайды. Баға қаралым болжамы емес.
YouTube Studio-дағы **Stayed to watch**, **Engaged views**, орташа көру
ұзақтығы және retention қисығымен қатар салыстырыңыз:
[Shorts analytics](https://support.google.com/youtube/answer/12942217?hl=en),
[audience retention](https://support.google.com/youtube/answer/9314415?hl=en),
[Shorts hook туралы YouTube](https://blog.youtube/creator-and-artist-stories/youtube-shorts-deep-dive/).

## 11. Жергілікті preview және автоматты тесттер

Тіркелгісіз, желісіз және жариялаусыз 540×960 MP4 үлгісі:

```sh
pip install -r requirements.txt
python preview_video.py --seed 42 --candidates 6 --fps 30 --output preview.mp4
```

Үлгіде синтезделген соққы дыбыстары бар; жанында JSON есебі сақталады.
Толық pipeline-ды желісіз тексеру үшін
`generate_video(skip_upload=True, offline=True, seed=42)` қолданыңыз.
`skip_upload=True` жалғыз өзі YouTube тарихын/музыкасын оқуға тыйым салмайды.

```sh
python -m unittest discover -s tests -p "test_*.py" -v
npm ci
npx playwright install chromium
npm test
```

Windows-та PowerShell `npm.ps1` файлын бұғаттаса, `npm.cmd`/`npx.cmd`
қолданыңыз. Орнатылған Chromium браузерін пайдалану үшін `WBA_BROWSER`
айнымалысына оның `.exe` жолын беруге болады.

Тесттер қаруларды, KO/replay күйін, FPS тәуелсіздігін, детерминизмді,
offline режимін, дыбыс таймлайнын және браузердегі негізгі әрекеттерді
тексереді. `.github/workflows/tests.yml` оларды CI-де іске қосады.

## 12. Қару балансын өлшеу

```sh
python analyze_balance.py --rounds 24 --seed 2026 --output balance_report.json
```

24 раунд — 312 дуэль; әр қару 24 рет қатысады. `score_rate` жеңіске бір,
double KO-ға жарты ұпай береді. Басқа seed-пен де тексеріңіз: шағын үлгідегі
пайыздар толық тең баланстың дәлелі емес. Урон түзетулері
`battle_sim.py` ішіндегі `WEAPON_DAMAGE_TUNING` кестесінде сақталған.

2026-10-18 жергілікті тексерісі: екі тәуелсіз seed жиынында 624 дуэль,
timeout жоқ; медиана тиісінше 12,863 және 13,254 секунд. Бұл — симуляция
диагностикасы, көрермен retention көрсеткіші емес.
