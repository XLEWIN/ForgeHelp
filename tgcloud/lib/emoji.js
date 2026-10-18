// Premium (custom) Telegram emoji helpers — port of help/helpbot/emojis.py.
// Display format (HTML parse mode ONLY):
//     <tg-emoji emoji-id="CUSTOM_EMOJI_ID">fallback</tg-emoji>
// Button labels and plain text keep the unicode fallback; Telegram cannot
// render custom emoji inside inline-keyboard labels.

/** Format a custom emoji as Telegram HTML (or the plain char if no id). */
export function customEmoji(emojiChar, customEmojiId) {
  if (!customEmojiId) return emojiChar;
  return `<tg-emoji emoji-id="${customEmojiId}">${emojiChar}</tg-emoji>`;
}

/** Replace <tg-emoji> tags with their inner fallback emoji. */
export function stripCustomEmoji(text) {
  return (text || '').replace(
    /<tg-emoji emoji-id="\d+">(.*?)<\/tg-emoji>/g,
    (_m, inner) => inner,
  );
}

/** key -> [custom emoji id, plain fallback]. Semantic keys so call sites
 *  read like intent (`uiTag("sparkle")`) rather than glyph names. */
export const UI_EMOJI_IDS = {
  // status / feedback
  check: ['5917917398572211635', '✅'],
  check_on: ['5915613625359278584', '✅'],
  check_done: ['5915722047513698700', '✅'],
  cross: ['5915894610709717241', '❌'],
  warn: ['5917860949817040467', '⚠️'],
  alert: ['5918260798387396946', '⚠️'],
  new: ['5917869294938497733', '🆕'],
  plus: ['5917908121442857117', '➕'],
  fire: ['5917806450977023726', '🔥'],
  rocket: ['5917935536219103066', '🚀'],
  sparkle: ['5915945987108511688', '✨'],
  // people / social
  user: ['5916034072592785479', '👤'],
  rival: ['5917987543978092091', '👤'],
  globe: ['5915728129187389553', '🌐'],
  region: ['5918273417001313756', '🌐'],
  chat: ['5915775824799211234', '💬'],
  mute: ['5915830538387595030', '🔈'],
  // rewards / shop / prestige
  star: ['5915719788360901158', '⭐'],
  gift: ['5917858965542150008', '🎁'],
  love: ['5918013330961735107', '😍'],
  crown: ['5918192804760133835', '👑'],
  cart: ['5917952668843648408', '🛒'],
  trophy: ['5915718748978814340', '🏆'],
  heart: ['5852755649405919501', '💙'],
  giggle: ['5852974147277169549', '🤭'],
  // power-ups
  mega: ['5917887935096561123', '💎'],
  zmove: ['5918152835794477491', '💎'],
  // move / stat views
  bolt: ['5852666434345248654', '⚡'],
  battle: ['5918013330961735107', '⚔️'],
  comet: ['5852826430466957463', '☄️'],
  aim: ['5852987088013633510', '➡️'],
  pp: ['5852755434657554545', '🔵'],
  status: ['5854846581219532134', '💤'],
  gem: ['5917887935096561123', '💎'],
  // aliases used by the (full-bot) Pokédex UI
  level: ['5852755434657554545', '🔵'],
  info: ['5915775824799211234', '💬'],
  circle: ['5854846581219532134', '💤'],
};

/** `<tg-emoji…>…</tg-emoji>` for a UI registry key (HTML only). */
export function uiTag(key, fallback = '') {
  const entry = UI_EMOJI_IDS[String(key || '').trim().toLowerCase()];
  if (!entry) return fallback;
  const [customId, plain] = entry;
  if (!customId) return fallback;
  return customEmoji(plain || fallback, customId);
}

/** Plain unicode glyph for a UI key — safe for button labels. */
export function uiGlyph(key, fallback = '') {
  const entry = UI_EMOJI_IDS[String(key || '').trim().toLowerCase()];
  if (!entry) return fallback;
  return entry[1] || fallback;
}

/** Custom-emoji id for a UI key — for button `icon_custom_emoji_id`. */
export function uiIconId(key) {
  const entry = UI_EMOJI_IDS[String(key || '').trim().toLowerCase()];
  return entry ? entry[0] : '';
}

// ── Ball / type / coin / shiny — the ones AI answers mention ─────────────

export const BALL_EMOJI_IDS = {
  'Poké Ball': '5852961356864561365',
  'Great Ball': '5915897634366695641',
  'Ultra Ball': '5915510236906529449',
  'Master Ball': '5916010141035013118',
  'Repeat Ball': '5915846142003781249',
  'Level Ball': '5915513002865468138',
  'Dusk Ball': '5915731968888152050',
  'Nest Ball': '5902528045419335365',
  'Safari Ball': '5915978143528656221',
};

export const BALL_FALLBACK = {
  'Poké Ball': '🔴', 'Great Ball': '🔵', 'Ultra Ball': '⚫',
  'Master Ball': '🟣', 'Repeat Ball': '🔴', 'Level Ball': '🟡',
  'Dusk Ball': '🟢', 'Nest Ball': '🟡', 'Safari Ball': '🟢',
};

export const BALL_ID_TO_NAME = {
  pokeball: 'Poké Ball', masterball: 'Master Ball',
  greatball: 'Great Ball', ultraball: 'Ultra Ball',
  repeatball: 'Repeat Ball', levelball: 'Level Ball',
  duskball: 'Dusk Ball', nestball: 'Nest Ball',
  safariball: 'Safari Ball',
};

/** Premium emoji HTML tag for a ball (icon only, HTML parse mode). */
export function ballTag(itemId) {
  if (!itemId) return '';
  const name = BALL_ID_TO_NAME[itemId.toLowerCase()]
    || itemId.replace(/-/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
  const plain = BALL_FALLBACK[name] || '🔴';
  return customEmoji(plain, BALL_EMOJI_IDS[name] || '');
}

export const TYPE_EMOJI_IDS = {
  Normal: '5915606195065856327',
  Fire: '5916011124582523123',
  Water: '5915535907926056421',
  Grass: '5915588474030792524',
  Electric: '5915517211933417386',
  Ice: '5915711722412318031',
  Fighting: '5915684543859269996',
  Poison: '5915673037641883235',
  Ground: '5915905872113967880',
  Flying: '5916033922268929532',
  Psychic: '5915889053022035072',
  Bug: '5915989297558725418',
  Rock: '5915947206879223885',
  Ghost: '5915832011561377693',
  Dragon: '5915653126173498505',
  Dark: '5915558916065862295',
  Steel: '5915622945438310975',
  Fairy: '5915510507489467989',
};

export const TYPE_FALLBACK = {
  Normal: '🟣', Fire: '🔥', Water: '💧', Grass: '🌿',
  Electric: '⚡', Ice: '❄️', Fighting: '🥊', Poison: '☠️',
  Ground: '🌍', Flying: '🕊️', Psychic: '🔮', Bug: '🐛',
  Rock: '🪨', Ghost: '👻', Dragon: '🐉', Dark: '🌑',
  Steel: '⚙️', Fairy: '🧚',
};

/** Custom-emoji HTML tag for a type (the icon only). */
export function typeTag(typeName) {
  if (!typeName) return '';
  const key = String(typeName).trim().toLowerCase()
    .replace(/\b\w/g, (c) => c.toUpperCase());
  const fallback = TYPE_FALLBACK[key] || '❔';
  return customEmoji(fallback, TYPE_EMOJI_IDS[key] || '');
}

/** `Fire <tg-emoji…>🔥</tg-emoji>` — type name followed by its icon. */
export function typeLabel(typeName) {
  if (!typeName) return '';
  return `${typeName} ${typeTag(typeName)}`;
}

/** `Fire <tag> / Water <tag>` for a list of types. */
export function typeLine(types) {
  return (types || []).filter(Boolean).map(typeLabel).join(' / ');
}

/** Forge Coins marker. */
export const COIN_EMOJI_ID = '5915882305628416528';

export function coinTag(fallback = '💰') {
  return customEmoji(fallback, COIN_EMOJI_ID);
}

/** Shiny marker. */
export const SHINY_EMOJI_ID = '5918098311184654030';

export function shinyTag(shiny = true, fallback = '✨') {
  if (!shiny) return '';
  return customEmoji(fallback, SHINY_EMOJI_ID);
}

// ── Convenience constants ({E.SPARKLE} in HTML messages) ─────────────────

/** Premium emoji constants for HTML messages only. */
export const E = {
  SPARKLE: uiTag('sparkle'),
  FIRE: uiTag('fire'),
  STAR: uiTag('star'),
  CHECK: uiTag('check'),
  CROSS: uiTag('cross'),
  WARN: uiTag('warn'),
  CROWN: uiTag('crown'),
  GIFT: uiTag('gift'),
  TROPHY: uiTag('trophy'),
  BATTLE: uiTag('battle'),
  REGION: uiTag('region'),
  CART: uiTag('cart'),
  GLOBE: uiTag('globe'),
  CHAT: uiTag('chat'),
  HEART: uiTag('heart'),
  ROCKET: uiTag('rocket'),
  NEW: uiTag('new'),
  USER: uiTag('user'),
  COIN: coinTag(),
  SHINY: shinyTag(),
  MEGA: uiTag('mega'),
  WELCOME: uiTag('sparkle'), // reuse sparkle for welcome flair
};
