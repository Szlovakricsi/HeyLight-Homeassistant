import { MODES } from "./card-helpers.js";

const ROWS = 17;
const rowCount = row => row + 4;
const totalBulbs = Array.from({ length: ROWS }, (_, row) => rowCount(row)).reduce((a, b) => a + b, 0);

function colorAt(palette, index) {
  return palette[index % Math.max(1, palette.length)] || "#fff";
}

export function treeHtml(effect, on, palette, speed) {
  const mode = MODES.get(effect) || "normal";
  const colors = palette.length ? palette : ["#ffffff"];
  const c1 = colorAt(colors, 0);
  const c2 = colorAt(colors, 1);
  const c3 = colorAt(colors, 2);
  const dur = Math.max(0.85, 4.55 - speed * 0.31);
  const long = dur * 4.8;
  const veryLong = dur * 7.4;
  let bulbs = "";
  let index = 0;
  let rowStart = 0;

  for (let row = 0; row < ROWS; row++) {
    const count = rowCount(row);
    const width = 12 + row * 4.82;
    const y = 14.8 + row * 4.42;
    for (let col = 0; col < count; col++, index++) {
      const x = 50 - width / 2 + (width * col) / (count - 1);
      const serpCol = row % 2 ? count - 1 - col : col;
      const path = rowStart + serpCol;
      const pf = path / Math.max(1, totalBulbs - 1);
      const rf = row / (ROWS - 1);
      const cf = col / Math.max(1, count - 1);
      const hash = (index * 37 + row * 17 + col * 11) % 101;
      const g3 = (row + col * 2) % 3;
      const g4 = (row * 2 + col) % 4;
      const vertical = Math.min(8, Math.max(0, Math.round(cf * 8)));
      const zone = Math.min(2, Math.floor((row / ROWS) * 3));
      const stripe = Math.floor(row / 2) % 3;
      const a = colorAt(colors, g3);
      const b = colorAt(colors, g3 + 1);
      const c = colorAt(colors, g3 + 2);
      const base = colorAt(colors, index);
      const flag = colorAt(colors, zone);
      const rowStripe = colorAt(colors, stripe);
      const verticalColor = colorAt(colors, vertical);
      const aroundDelay = -(g4 * (dur * 1.18 / 4));
      const patternDelay = -(g3 * (dur * 0.92 / 3));
      const growDownDelay = row * (veryLong * 0.036);
      const growUpDelay = (ROWS - 1 - row) * (long * 0.043);
      const bandDelay = row * (long * 0.047);
      const collideDelay = Math.min(row, ROWS - 1 - row) * (dur * 0.115);
      const verticalDelay = vertical * (long * 0.062);
      const pathDelay = path * (dur * 0.018);
      const star = hash < 19 ? 1 : 0;
      const accent = hash < 24 ? 1 : hash > 82 ? 2 : 0;

      bulbs += `<i class="bulb ${star ? "is-star" : ""} accent-${accent}" style="left:${x.toFixed(2)}%;top:${y.toFixed(2)}%;--base:${base};--a:${a};--b:${b};--c:${c};--flag:${flag};--stripe:${rowStripe};--vcolor:${verticalColor};--r:${row};--rf:${rf.toFixed(4)};--cf:${cf.toFixed(4)};--pf:${pf.toFixed(4)};--hash:${hash};--around:${aroundDelay.toFixed(3)}s;--pattern:${patternDelay.toFixed(3)}s;--growd:${growDownDelay.toFixed(3)}s;--growu:${growUpDelay.toFixed(3)}s;--bandd:${bandDelay.toFixed(3)}s;--cold:${collideDelay.toFixed(3)}s;--vd:${verticalDelay.toFixed(3)}s;--pathd:${pathDelay.toFixed(3)}s"></i>`;
    }
    rowStart += count;
  }

  return `<div class="tree ${on ? "on" : "off"} fx-${mode}" style="--c1:${c1};--c2:${c2};--c3:${c3};--dur:${dur.toFixed(2)}s;--long:${long.toFixed(2)}s;--vlong:${veryLong.toFixed(2)}s"><b class="halo"></b><b class="star">★</b><b class="canopy"></b>${bulbs}<b class="trunk"></b><b class="ground"></b></div>`;
}

export const TREE_CSS = `
.visual-shell{position:relative;min-height:448px;margin:0 0 8px;overflow:visible}.visual{position:absolute;inset:0;display:flex;align-items:flex-start;justify-content:center;padding-top:22px;overflow:visible}.effect-side{position:absolute;z-index:9;right:0;top:48%;transform:translateY(-50%);width:102px;padding:12px 10px;border-radius:16px;background:color-mix(in srgb,var(--secondary-background-color) 78%,transparent);border:1px solid color-mix(in srgb,var(--divider-color) 68%,transparent);backdrop-filter:blur(10px);min-width:0}.effect-side small{display:block;font-size:10px;color:var(--secondary-text-color);margin-bottom:4px}.effect-side strong{display:block;font-size:13px;line-height:1.25;word-break:break-word}.tree{position:relative;width:min(79%,322px);aspect-ratio:.79;transform:translateX(-25px);overflow:visible}.canopy{position:absolute;left:50%;top:11.5%;width:91%;height:78%;transform:translateX(-50%);clip-path:polygon(50% 0,100% 100%,0 100%);background:linear-gradient(160deg,rgba(18,79,61,.20),rgba(3,24,31,.49));filter:drop-shadow(0 14px 28px rgba(0,0,0,.18))}.halo{position:absolute;inset:2% 0 7%;border-radius:50%;background:radial-gradient(circle,color-mix(in srgb,var(--c1) 14%,transparent),transparent 64%);filter:blur(20px)}.off .halo{opacity:.13}.star{position:absolute;z-index:6;left:50%;top:-4px;transform:translateX(-50%);font-size:44px;line-height:1;color:#ffc64b;text-shadow:0 0 22px rgba(255,198,75,.58);overflow:visible}.off .star{color:#667;text-shadow:none}.trunk{position:absolute;left:50%;bottom:2.4%;width:17%;height:15%;transform:translateX(-50%);clip-path:polygon(28% 0,72% 0,100% 100%,0 100%);background:linear-gradient(#8f5a4d,#56352f)}.ground{position:absolute;left:14%;right:14%;bottom:1.7%;height:5px;border-radius:50%;background:radial-gradient(ellipse,rgba(255,255,255,.68),transparent)}
.tree .bulb{position:absolute;z-index:4;width:7.6px;height:7.6px;transform:translate(-50%,-50%);border-radius:50%;background:var(--base);opacity:.98;box-shadow:0 0 4px var(--base),0 0 10px color-mix(in srgb,var(--base) 58%,transparent);will-change:opacity,filter,background,transform}.tree .bulb::after{content:"";position:absolute;inset:0;border-radius:inherit;background:transparent;opacity:0}.off .bulb{background:#11151f!important;opacity:.53!important;box-shadow:none!important;animation:none!important}.off .bulb::after{display:none!important}
.fx-normal.on .bulb{background:var(--c1);box-shadow:0 0 4px var(--c1),0 0 10px color-mix(in srgb,var(--c1) 58%,transparent)}
.fx-flick.on .bulb{animation:flickAll var(--dur) steps(1,end) infinite}
.fx-flick-around.on .bulb{background:var(--c1);opacity:.055;box-shadow:none;animation:flickAround calc(var(--dur)*1.18) steps(1,end) infinite;animation-delay:var(--around)}
.fx-random-color.on .bulb{background:hsl(calc(var(--hash)*3.56) 88% 60%);box-shadow:0 0 5px hsl(calc(var(--hash)*3.56) 88% 60%),0 0 11px hsl(calc(var(--hash)*3.56) 88% 60%/.48);animation:randomColor calc(var(--dur)*1.35) steps(4,end) infinite;animation-delay:calc(var(--hash)*-.013s)}
.fx-fading.on .bulb{background:var(--c1);animation:fading var(--dur) ease-in-out infinite}
.fx-fading-adv.on .bulb{animation:fadingAdv calc(var(--dur)*2.7) ease-in-out infinite}
.fx-color-change1.on .bulb{animation:colorChange1 calc(var(--dur)*1.35) steps(1,end) infinite}
.fx-color-change2.on .bulb{animation:colorChange2 calc(var(--dur)*.92) steps(1,end) infinite;animation-delay:var(--pattern)}
.fx-fall-rainbow.on .bulb{background:hsl(calc(var(--r)*23 + var(--cf)*20) 92% 57%);opacity:.035;box-shadow:none;animation:growDownRainbow var(--vlong) linear infinite;animation-delay:var(--growd)}
.fx-fall-snake.on .bulb{background:var(--c1);opacity:.025;box-shadow:none;animation:growDownSolid var(--long) linear infinite;animation-delay:var(--growd)}
.fx-fall-ant.on .bulb{background:var(--c1);opacity:.025;box-shadow:none;animation:fallBand var(--long) ease-in-out infinite;animation-delay:var(--bandd)}
.fx-moon-stars.on .bulb{background:#11151f;opacity:.28;box-shadow:none}.fx-moon-stars.on .bulb.is-star{background:var(--a);animation:starTwinkle calc(var(--dur)*1.8) ease-in-out infinite;animation-delay:calc(var(--hash)*-.041s);box-shadow:0 0 5px var(--a),0 0 12px color-mix(in srgb,var(--a) 55%,transparent)}
.fx-collide.on .bulb{background:var(--a);opacity:.035;box-shadow:none;animation:collideBands calc(var(--dur)*2.1) ease-in-out infinite;animation-delay:var(--cold)}
.fx-little-fire.on .bulb{background:var(--stripe);animation:littleFire calc(var(--dur)*2.0) ease-in-out infinite;animation-delay:calc(var(--r)*-.055s)}
.fx-random-breath.on .bulb{background:var(--c1);animation:baseBreath calc(var(--dur)*1.65) ease-in-out infinite}.fx-random-breath.on .bulb.accent-1{background:var(--c2);animation:accentBreath calc(var(--dur)*1.35) ease-in-out infinite;animation-delay:calc(var(--hash)*-.027s)}.fx-random-breath.on .bulb.accent-2{background:var(--c3);animation:accentBreath calc(var(--dur)*1.55) ease-in-out infinite;animation-delay:calc(var(--hash)*-.031s)}
.fx-wave-up.on .bulb{background:var(--stripe);opacity:.025;box-shadow:none;animation:waveGrow var(--long) linear infinite;animation-delay:var(--growu)}
.fx-wave-down.on .bulb{background:var(--stripe);opacity:.025;box-shadow:none;animation:waveGrow var(--long) linear infinite;animation-delay:var(--growd)}
.fx-flag.on .bulb{background:var(--flag);animation:flagBreath calc(var(--dur)*1.35) ease-in-out infinite}
.fx-heap-up.on .bulb{background:var(--c1);opacity:.025;box-shadow:none;animation:heapStack var(--vlong) steps(1,end) infinite;animation-delay:var(--growu)}.fx-heap-up.on .bulb::after{background:var(--c1);box-shadow:0 0 4px var(--c1),0 0 10px color-mix(in srgb,var(--c1) 58%,transparent);animation:heapFaller calc(var(--dur)*2.15) linear infinite;animation-delay:var(--bandd)}
.fx-vertical-wave.on .bulb{background:var(--vcolor);opacity:.025;box-shadow:none;animation:verticalGrow var(--long) linear infinite;animation-delay:var(--vd)}
.fx-snake.on .bulb{background:#11151f;opacity:.22;box-shadow:none;animation:snakePath calc(var(--dur)*4.2) linear infinite;animation-delay:var(--pathd)}
@keyframes flickAll{0%,21%{background:var(--c1);opacity:1}22%,43%{background:var(--c2);opacity:.96}44%,65%{background:var(--c3);opacity:1}66%,77%{opacity:.18}78%,100%{background:var(--c1);opacity:1}}
@keyframes flickAround{0%,18%{opacity:1;box-shadow:0 0 5px var(--c1),0 0 12px color-mix(in srgb,var(--c1) 58%,transparent);transform:translate(-50%,-50%) scale(1.12)}19%,100%{opacity:.035;box-shadow:none;transform:translate(-50%,-50%) scale(.78)}}
@keyframes randomColor{0%{filter:hue-rotate(0deg)}25%{filter:hue-rotate(75deg)}50%{filter:hue-rotate(170deg)}75%{filter:hue-rotate(260deg)}100%{filter:hue-rotate(360deg)}}
@keyframes fading{0%,100%{opacity:.08;filter:brightness(.45)}50%{opacity:1;filter:brightness(1.25)}}
@keyframes fadingAdv{0%,8%{background:var(--c1);opacity:.08}16%{background:var(--c1);opacity:1}27%{background:var(--c1);opacity:.08}34%{background:var(--c2);opacity:.08}43%{background:var(--c2);opacity:1}54%{background:var(--c2);opacity:.08}63%{background:var(--c3);opacity:.08}73%{background:var(--c3);opacity:1}86%{background:var(--c3);opacity:.08}100%{background:var(--c1);opacity:.08}}
@keyframes colorChange1{0%,24%{background:var(--c1)}25%,49%{background:var(--c2)}50%,74%{background:var(--c3)}75%,100%{background:var(--c1)}}
@keyframes colorChange2{0%,31%{background:var(--a)}32%,64%{background:var(--b)}65%,100%{background:var(--c)}}
@keyframes growDownRainbow{0%,5%{opacity:.025;box-shadow:none}9%,78%{opacity:1;box-shadow:0 0 5px currentColor,0 0 11px currentColor}88%,100%{opacity:.025;box-shadow:none}}
@keyframes growDownSolid{0%,6%{opacity:.025;box-shadow:none}10%,80%{opacity:1;box-shadow:0 0 5px var(--c1),0 0 11px color-mix(in srgb,var(--c1) 60%,transparent)}90%,100%{opacity:.025;box-shadow:none}}
@keyframes fallBand{0%,72%,100%{opacity:.025;box-shadow:none;transform:translate(-50%,-50%) scale(.82)}78%,90%{opacity:1;box-shadow:0 0 5px var(--c1),0 0 12px color-mix(in srgb,var(--c1) 58%,transparent);transform:translate(-50%,-50%) scale(1.08)}}
@keyframes starTwinkle{0%,73%,100%{opacity:.08;transform:translate(-50%,-50%) scale(.65)}82%{opacity:1;transform:translate(-50%,-50%) scale(1.32)}90%{opacity:.28}}
@keyframes collideBands{0%,70%,100%{opacity:.025;box-shadow:none;transform:translate(-50%,-50%) scale(.78)}76%,89%{opacity:1;box-shadow:0 0 5px var(--a),0 0 12px color-mix(in srgb,var(--a) 58%,transparent);transform:translate(-50%,-50%) scale(1.08)}}
@keyframes littleFire{0%,100%{opacity:.28;filter:brightness(.7);transform:translate(-50%,-50%) scale(.93)}18%{background:var(--c1);opacity:1}40%{background:var(--c2);opacity:.72}62%{background:var(--c3);opacity:1}82%{background:var(--c1);opacity:.55;filter:brightness(1.28);transform:translate(-50%,-50%) scale(1.08)}}
@keyframes baseBreath{0%,100%{opacity:.58;filter:brightness(.78)}50%{opacity:1;filter:brightness(1.17)}}
@keyframes accentBreath{0%,100%{opacity:.08;transform:translate(-50%,-50%) scale(.72)}50%{opacity:1;transform:translate(-50%,-50%) scale(1.17)}}
@keyframes waveGrow{0%,5%{opacity:.025;box-shadow:none}10%,79%{opacity:1;box-shadow:0 0 5px var(--stripe),0 0 11px color-mix(in srgb,var(--stripe) 58%,transparent)}89%,100%{opacity:.025;box-shadow:none}}
@keyframes flagBreath{0%,100%{opacity:.08;filter:brightness(.55)}48%,70%{opacity:1;filter:brightness(1.18)}}
@keyframes heapStack{0%,9%{opacity:.025;box-shadow:none}13%,79%{opacity:1;box-shadow:0 0 5px var(--c1),0 0 11px color-mix(in srgb,var(--c1) 58%,transparent)}89%,100%{opacity:.025;box-shadow:none}}
@keyframes heapFaller{0%,73%,100%{opacity:0;transform:scale(.76)}78%,89%{opacity:1;transform:scale(1.08)}}
@keyframes verticalGrow{0%,5%{opacity:.025;box-shadow:none}10%,80%{opacity:1;box-shadow:0 0 5px var(--vcolor),0 0 11px color-mix(in srgb,var(--vcolor) 58%,transparent)}90%,100%{opacity:.025;box-shadow:none}}
@keyframes snakePath{0%,6%{background:var(--c1);opacity:1;box-shadow:0 0 5px var(--c1),0 0 12px color-mix(in srgb,var(--c1) 58%,transparent);transform:translate(-50%,-50%) scale(1.12)}7%,58%{background:#11151f;opacity:.16;box-shadow:none;transform:translate(-50%,-50%) scale(.82)}60%,62%{background:var(--c2);opacity:1;box-shadow:0 0 5px var(--c2),0 0 12px color-mix(in srgb,var(--c2) 58%,transparent);transform:translate(-50%,-50%) scale(1.16)}63%,100%{background:#11151f;opacity:.16;box-shadow:none;transform:translate(-50%,-50%) scale(.82)}}
@media(max-width:600px){.visual-shell{min-height:430px}.visual{padding-top:20px}.tree{width:min(84%,306px);aspect-ratio:.78;transform:translateX(-18px)}.effect-side{right:-2px;width:92px;padding:10px 8px}.effect-side strong{font-size:12px}.tree .bulb{width:7.2px;height:7.2px}.star{top:-5px;font-size:43px}}
@media(max-width:390px){.visual-shell{min-height:414px}.tree{width:min(85%,288px);transform:translateX(-16px)}.effect-side{width:86px}.tree .bulb{width:6.8px;height:6.8px}}
@media(prefers-reduced-motion:reduce){.tree .bulb,.tree .bulb::after{animation:none!important}}`;
