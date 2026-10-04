export const VERSION = "0.5.1";

export const TEXT = {
  en: {
    on: "On", off: "Off", unavailable: "Unavailable", effect: "Effect",
    brightness: "Brightness", speed: "Effect speed", primary: "Primary",
    secondary: "Color 2", tertiary: "Color 3", enabled: "Enabled",
    disabled: "Disabled", internal: "Effect colors", noExtra: "Not used by this effect",
    selectLight: "HeyLight light", choose: "Choose a HeyLight light",
    auto: "Color 2, Color 3 and speed are discovered automatically from the same device."
  },
  hu: {
    on: "Bekapcsolva", off: "Kikapcsolva", unavailable: "Nem elérhető", effect: "Effekt",
    brightness: "Fényerő", speed: "Effektsebesség", primary: "Főszín",
    secondary: "2. szín", tertiary: "3. szín", enabled: "Aktív",
    disabled: "Kikapcsolva", internal: "Az effekt saját színei", noExtra: "Ez az effekt nem használja",
    selectLight: "HeyLight fényfüzér", choose: "Válassz HeyLight fényfüzért",
    auto: "A 2. és 3. színt, valamint az effektsebességet automatikusan megkeresi ugyanazon az eszközön."
  }
};

export const MODES = new Map([
  ["normal","normal"],["flick","flick"],["flick around","flick-around"],["random color","random-color"],
  ["fading","fading"],["fading adv","fading-adv"],["color change1","color-change1"],["color change2","color-change2"],
  ["fall rainbow","fall-rainbow"],["fall snake","fall-snake"],["fall ant","fall-ant"],["moon beyond stars","moon-stars"],
  ["collide","collide"],["little fire","little-fire"],["random breath","random-breath"],["wave down","wave-down"],
  ["flag","flag"],["heap up","heap-up"],["vertical wave","vertical-wave"],["snake","snake"],["wave up","wave-up"]
]);

export const INTERNAL = new Set(["random color", "fall rainbow"]);
export const clamp = (v, a, b) => Math.max(a, Math.min(b, v));

export function rgbToHex(rgb) {
  if (!Array.isArray(rgb) || rgb.length < 3) return "#ffffff";
  return `#${rgb.slice(0,3).map(v => clamp(Number(v)||0,0,255).toString(16).padStart(2,"0")).join("")}`;
}
export function hexToRgb(hex) {
  const s = String(hex || "#ffffff").replace("#", "");
  return /^[0-9a-f]{6}$/i.test(s) ? [0,2,4].map(i => parseInt(s.slice(i,i+2),16)) : [255,255,255];
}
export function esc(v) {
  return String(v ?? "").replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;").replaceAll('"',"&quot;").replaceAll("'","&#039;");
}
export const pretty = e => e ? e.replace(/\b\w/g, c => c.toUpperCase()) : "—";
