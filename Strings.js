.pragma library

// Every user-visible word of the widget, in each supported language.
// {name} placeholders are filled by t(); tests keep both tables in step.

var en = {
  loading: "Loading…",
  tipLoading: "Claude · loading…",
  tipHint: "Click for details",
  tipSession: "5-hour window: {pct}% · {status}",
  tipReset: " · resets {when}",
  tipWeek: "Week: {pct}% · {status} · resets {when}",
  updated: "updated {time}",
  noData: "no data",
  refreshTip: "Refresh · R",
  showDetails: "Details · D",
  hideDetails: "Fewer details · D",

  session: "5-hour window",
  week: "Week",
  modelWeek: "{model} · week",
  weekShort: "W",
  barClosed: "5h",

  statusNew: "not started",
  statusSpent: "limit reached",
  statusRunsOut: "will run out",
  statusOverShare: "over weekly share",
  statusFast: "spending fast",
  statusNear: "near the limit",
  statusUnused: "not in use",
  statusOk: "on track",

  sumClosed: "The window opens with your first message.",
  sumSpent: "The limit is used up. It resets at {when}, in {left}.",
  sumRunsOut: "At this speed the limit runs out at {when}, in {left} — before the reset.",
  sumOverShare: "This window is using more than its share of the week. Slow down so the week lasts.",
  sumFast: "You are spending faster than an even pace, but the limit is not at risk yet.",
  sumNear: "At this speed you will reach about {pct}% by the reset — close to the limit.",
  sumUnused: "Nothing is being used right now.",
  sumOk: "You are on track.",
  sumOkForecast: "You are on track: about {pct}% by the reset.",

  rowReset: "Resets",
  rowResetValue: "{when} (in {left})",
  rowKeepUnder: "Keep under",
  rowKeepUnderCapped: "{pct}% — this window is worth about {share}% of your week",
  rowKeepUnderFree: "the week does not limit this window",
  rowEven: "Even pace",
  rowEvenValue: "{pct}% by now · {diff}",
  diffSame: "you are right on it",
  diffMore: "you spent {n}% more",
  diffLess: "you spent {n}% less",
  rowSafe: "Safe speed",
  rowSafeValue: "up to {rate}",
  rowYours: "Your speed",
  yoursRecent: "{rate} (last 30 min)",
  yoursAverage: "{rate} (average for the window)",
  yoursWeekly: "{rate} (over your active hours)",
  yoursIdle: "not spending right now",
  yoursMeasuring: "measuring…",
  rowForecast: "Forecast",
  forecastRunsOut: "runs out at {when}, in {left}",
  forecastOverShare: "about {pct}% by the reset — over this window's share",
  forecastPlain: "about {pct}% by the reset",

  ratePerHour: "{n}% per hour",
  ratePerDay: "{n}% per day",

  legendEven: "even pace",
  legendForecast: "forecast at reset",
  legendShare: "beyond weekly share",
  footnote: "Fill past the dark mark means you spend faster than an even pace. The week is counted over your active hours, {from}:00–{to}:00. The 5-hour window is capped so the week lasts. All devices on your account are counted.",

  staleExpired: "Claude Code sign-in expired — run claude",
  staleAuth: "not signed in to Claude Code",
  staleRate: "the server asks to wait",
  staleNetwork: "no network",
  noLimits: "No limit data: {why}",

  unitD: "d", unitH: "h", unitM: "m", unitMin: "min",
  tomorrow: "tomorrow",
  am: "AM", pm: "PM",
  wd0: "Sun", wd1: "Mon", wd2: "Tue", wd3: "Wed", wd4: "Thu", wd5: "Fri", wd6: "Sat"
}

var ru = {
  loading: "Загрузка…",
  tipLoading: "Claude · загрузка…",
  tipHint: "Клик — подробности",
  tipSession: "5 часов: {pct}% · {status}",
  tipReset: " · сброс {when}",
  tipWeek: "Неделя: {pct}% · {status} · сброс {when}",
  updated: "обновлено {time}",
  noData: "нет данных",
  refreshTip: "Обновить · R",
  showDetails: "Подробнее · D",
  hideDetails: "Короче · D",

  session: "Окно 5 часов",
  week: "Неделя",
  modelWeek: "{model} · неделя",
  weekShort: "н",
  barClosed: "5ч",

  statusNew: "не начато",
  statusSpent: "лимит исчерпан",
  statusRunsOut: "скоро кончится",
  statusOverShare: "больше доли недели",
  statusFast: "тратите быстро",
  statusNear: "близко к лимиту",
  statusUnused: "не используется",
  statusOk: "всё в порядке",

  sumClosed: "Окно откроется с вашего первого сообщения.",
  sumSpent: "Лимит исчерпан. Сброс в {when}, через {left}.",
  sumRunsOut: "При такой скорости лимит кончится в {when}, через {left} — раньше сброса.",
  sumOverShare: "Это окно тратит больше своей доли недели. Притормозите, чтобы хватило на всю неделю.",
  sumFast: "Вы тратите быстрее ровного темпа, но лимиту пока ничего не угрожает.",
  sumNear: "При такой скорости к сбросу будет около {pct}% — близко к лимиту.",
  sumUnused: "Сейчас ничего не тратится.",
  sumOk: "Всё идёт хорошо.",
  sumOkForecast: "Всё идёт хорошо: к сбросу будет около {pct}%.",

  rowReset: "Сброс",
  rowResetValue: "{when} (через {left})",
  rowKeepUnder: "Не выше",
  rowKeepUnderCapped: "{pct}% — это окно стоит около {share}% недели",
  rowKeepUnderFree: "неделя это окно не ограничивает",
  rowEven: "Ровный темп",
  rowEvenValue: "сейчас {pct}% · {diff}",
  diffSame: "вы точно в темпе",
  diffMore: "вы потратили на {n}% больше",
  diffLess: "вы потратили на {n}% меньше",
  rowSafe: "Безопасная скорость",
  rowSafeValue: "до {rate}",
  rowYours: "Ваша скорость",
  yoursRecent: "{rate} (за последние 30 мин)",
  yoursAverage: "{rate} (в среднем за окно)",
  yoursWeekly: "{rate} (по часам вашей работы)",
  yoursIdle: "сейчас не тратите",
  yoursMeasuring: "измеряю…",
  rowForecast: "Прогноз",
  forecastRunsOut: "кончится в {when}, через {left}",
  forecastOverShare: "около {pct}% к сбросу — больше доли этого окна",
  forecastPlain: "около {pct}% к сбросу",

  ratePerHour: "{n}% в час",
  ratePerDay: "{n}% в день",

  legendEven: "ровный темп",
  legendForecast: "прогноз к сбросу",
  legendShare: "сверх доли недели",
  footnote: "Заливка правее тёмной черты — вы тратите быстрее ровного темпа. Неделя считается по вашим рабочим часам, {from}:00–{to}:00. Окно 5 часов ограничено так, чтобы хватило на всю неделю. Учтены все устройства вашего аккаунта.",

  staleExpired: "вход в Claude Code истёк — запустите claude",
  staleAuth: "нет входа в Claude Code",
  staleRate: "сервер просит подождать",
  staleNetwork: "нет сети",
  noLimits: "Нет данных о лимитах: {why}",

  unitD: "д", unitH: "ч", unitM: "м", unitMin: "мин",
  tomorrow: "завтра",
  am: "AM", pm: "PM",
  wd0: "вс", wd1: "пн", wd2: "вт", wd3: "ср", wd4: "чт", wd5: "пт", wd6: "сб"
}

var TABLES = { en: en, ru: ru }
var LANGS = ["en", "ru"]

// "auto" follows the system locale (ru_RU.UTF-8 → ru); anything unknown is English.
function resolve(setting, locale) {
  var s = String(setting || "auto").toLowerCase()
  if (LANGS.indexOf(s) >= 0) return s
  if (s === "русский") return "ru"
  if (s === "english") return "en"
  var l = String(locale || "").toLowerCase()
  for (var i = 0; i < LANGS.length; i++)
    if (l === LANGS[i] || l.indexOf(LANGS[i] + "_") === 0 || l.indexOf(LANGS[i] + "-") === 0) return LANGS[i]
  return "en"
}

function t(lang, key, params) {
  var table = TABLES[lang] || en
  var text = table[key]
  if (text === undefined) text = en[key]
  if (text === undefined) return key
  return text.replace(/\{(\w+)\}/g, function(m, name) {
    return params && params[name] !== undefined ? params[name] : m
  })
}

// 7.2 → "7.2" in English, "7,2" in Russian.
function num(lang, n, digits) {
  var s = Number(n).toFixed(digits === undefined ? 0 : digits)
  return lang === "ru" ? s.replace(".", ",") : s
}
