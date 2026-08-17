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
- **18 қару түрінен** (Sword, Katana, Axe, Hammer, Warhammer, Spear, Trident,
  Dagger, Kunai, Mace, Flail, Nunchaku, Whip, Scythe, Claws, Chainsaw, Staff,
  Shuriken) кездейсоқ **2, 3 немесе 4-уін** таңдайды (салмақталған: 55% — 1v1
  дуэль, 28% — 3-жақты, 17% — 4-жақты "battle royale"), әрқайсысын PIL-мен
  геометриялық фигура ретінде салады (нақты сурет/фото жоқ — Content ID claim
  мүлдем болмайды, басқа ойындардың арт-активтері көшірілмейді, тек
  концепция-алуан түрлілігінен шабыттанған original дизайн);
- **10 арена-тақырыбынан** (Midnight Arena, Neon City, Lava Pit, Ice Cave,
  Cyber Grid, Deep Space, Toxic Lab, Sunset Coliseum, Volcanic Forge, Frozen
  Peak) біреуін кездейсоқ таңдайды — градиент түсі, тор түсі, қалқымалы
  бөлшектер бәрі тақырыпқа сай өзгереді, сондықтан күнделікті видеолар
  бір-біріне ұқсамайды;
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
2 қарудың C(18,2)=153 + 3 қарудың C(18,3)=816 + 4 қарудың C(18,4)=3060
комбинациясы × 10 арена = **40 000+ бірегей видео нұсқасы**.

## 6. Монетизация туралы маңызды ескерту

- Толығымен генерацияланған физика/визуал + Openverse CC музыка + numpy-мен
  синтезделген SFX — copyright claim тәуекелі жоқтың қасы.
- YouTube Partner Program-ге өту үшін арна **1000 жазылушы + 4000 сағат watch
  time (12 айда)** шегіне жетуі керек — бот тек контентті тұрақты шығарады.

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
