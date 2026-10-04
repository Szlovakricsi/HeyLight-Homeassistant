import { MODES } from "./card-helpers.js";

export function treeHtml(effect, on, palette, speed) {
  const mode = MODES.get(effect) || "normal";
  let bulbs = "", i = 0;
  for (let row=0; row<14; row++) {
    const count=row+4, width=16+row*5.1, y=16+row*5.45;
    for (let col=0; col<count; col++,i++) {
      const x=50-width/2+(width*col)/(count-1);
      const base=palette[i%palette.length]||"#fff";
      bulbs += `<i style="left:${x.toFixed(2)}%;top:${y.toFixed(2)}%;--base:${base};--r:${row};--c:${col};--n:${i};--h:${(i*31+row*17)%360};--seq:${(-i*.055).toFixed(3)}s;--rowd:${(-row*.16).toFixed(3)}s;--rowu:${(row*.16).toFixed(3)}s;--cold:${(-col*.12).toFixed(3)}s;--rnd:${(-((i*37)%29)*.09).toFixed(3)}s"></i>`;
    }
  }
  const d=Math.max(.7,3.2-speed*.23);
  return `<div class="tree ${on?"on":"off"} fx-${mode}" style="--c1:${palette[0]||"#fff"};--c2:${palette[1]||palette[0]||"#fff"};--c3:${palette[2]||palette[1]||palette[0]||"#fff"};--dur:${d.toFixed(2)}s;--fast:${(d*.55).toFixed(2)}s;--slow:${(d*1.55).toFixed(2)}s"><b class="halo"></b><b class="star">★</b><b class="canopy"></b>${bulbs}<b class="trunk"></b><b class="ground"></b></div>`;
}

export const TREE_CSS = `
.visual-shell{display:grid;grid-template-columns:minmax(0,1fr) 112px;align-items:center;gap:4px;margin:2px 0 8px}.visual{position:relative;min-height:355px;display:flex;align-items:center;justify-content:center}.effect-side{align-self:center;padding:12px 10px;border-radius:16px;background:color-mix(in srgb,var(--secondary-background-color) 70%,transparent);border:1px solid color-mix(in srgb,var(--divider-color) 62%,transparent);min-width:0}.effect-side small{display:block;font-size:10px;color:var(--secondary-text-color);margin-bottom:4px}.effect-side strong{display:block;font-size:13px;line-height:1.25;word-break:break-word}.tree{position:relative;width:min(100%,330px);aspect-ratio:1/1.09}.canopy{position:absolute;left:50%;top:12%;width:89%;height:78%;transform:translateX(-50%);clip-path:polygon(50% 0,100% 100%,0 100%);background:linear-gradient(160deg,rgba(18,79,61,.22),rgba(3,24,31,.50));filter:drop-shadow(0 14px 28px rgba(0,0,0,.18))}.halo{position:absolute;inset:4% 2% 8%;border-radius:50%;background:radial-gradient(circle,color-mix(in srgb,var(--c1) 14%,transparent),transparent 65%);filter:blur(18px)}.off .halo{opacity:.18}.star{position:absolute;z-index:5;left:50%;top:0;transform:translateX(-50%);font-size:42px;line-height:1;color:#ffc64b;text-shadow:0 0 22px rgba(255,198,75,.55)}.off .star{color:#667;text-shadow:none}.trunk{position:absolute;left:50%;bottom:2.5%;width:17%;height:16%;transform:translateX(-50%);clip-path:polygon(28% 0,72% 0,100% 100%,0 100%);background:linear-gradient(#8f5a4d,#56352f)}.ground{position:absolute;left:14%;right:14%;bottom:1.8%;height:5px;border-radius:50%;background:radial-gradient(ellipse,rgba(255,255,255,.68),transparent)}.tree i{position:absolute;z-index:4;width:8px;height:8px;transform:translate(-50%,-50%);border-radius:50%;background:var(--base);opacity:.96;box-shadow:0 0 4px var(--base),0 0 10px color-mix(in srgb,var(--base) 58%,transparent);will-change:transform,opacity,filter,background}.off i{background:#131722!important;opacity:.52!important;box-shadow:none!important;animation:none!important}
.fx-normal.on i{background:var(--c1)}
.fx-flick.on i{background:var(--c1);animation:flick var(--fast) infinite steps(2,end);animation-delay:var(--rnd)}
.fx-flick-around.on i{background:var(--c1);animation:flickAround var(--slow) linear infinite;animation-delay:var(--seq)}
.fx-random-color.on i{background:hsl(var(--h) 92% 58%);box-shadow:0 0 5px hsl(var(--h) 92% 58%),0 0 11px hsl(var(--h) 92% 58%/.5);animation:randomColor var(--slow) steps(4,end) infinite;animation-delay:var(--rnd)}
.fx-fading.on i{background:var(--c1);animation:wholeFade var(--dur) ease-in-out infinite}
.fx-fading-adv.on i{animation:paletteFade var(--slow) ease-in-out infinite}
.fx-color-change1.on i{animation:wholePalette var(--dur) steps(1,end) infinite}
.fx-color-change2.on i{animation:stripePalette var(--slow) linear infinite;animation-delay:var(--rowd)}
.fx-fall-rainbow.on i{background:hsl(calc(var(--r)*24 + var(--c)*7) 92% 58%);box-shadow:0 0 5px currentColor;animation:rainFall var(--slow) linear infinite;animation-delay:var(--rowd)}
.fx-fall-snake.on i{background:var(--base);animation:snakeTrail var(--slow) linear infinite;animation-delay:var(--seq)}
.fx-fall-ant.on i{background:var(--base);animation:antTrail var(--dur) linear infinite;animation-delay:var(--seq)}
.fx-moon-stars.on i{background:var(--c1);animation:moonStars var(--slow) ease-in-out infinite;animation-delay:var(--rnd)}
.fx-collide.on i{background:var(--base);animation:collide var(--dur) ease-in-out infinite;animation-delay:var(--cold)}
.fx-little-fire.on i{background:var(--c1);animation:fire var(--fast) infinite alternate;animation-delay:var(--rnd)}
.fx-random-breath.on i{background:var(--base);animation:randomBreath var(--slow) ease-in-out infinite;animation-delay:var(--rnd)}
.fx-wave-down.on i{background:var(--base);animation:rowWave var(--dur) ease-in-out infinite;animation-delay:var(--rowd)}
.fx-flag.on i{background:var(--base);animation:flagWave var(--slow) ease-in-out infinite;animation-delay:var(--rowd)}
.fx-heap-up.on i{background:var(--c1);animation:heapUp var(--slow) linear infinite;animation-delay:var(--rowu)}
.fx-vertical-wave.on i{background:var(--base);animation:verticalWave var(--dur) ease-in-out infinite;animation-delay:var(--cold)}
.fx-snake.on i{background:var(--base);animation:snakeTrail var(--dur) linear infinite;animation-delay:var(--seq)}
.fx-wave-up.on i{background:var(--base);animation:rowWave var(--dur) ease-in-out infinite;animation-delay:var(--rowu)}
@keyframes flick{0%,48%{opacity:.16;transform:translate(-50%,-50%) scale(.72)}49%,100%{opacity:1;transform:translate(-50%,-50%) scale(1.12)}}
@keyframes flickAround{0%,78%{opacity:.08}83%,93%{opacity:1;transform:translate(-50%,-50%) scale(1.23)}100%{opacity:.08}}
@keyframes randomColor{0%{filter:hue-rotate(0deg)}25%{filter:hue-rotate(95deg)}50%{filter:hue-rotate(185deg)}75%{filter:hue-rotate(270deg)}100%{filter:hue-rotate(360deg)}}
@keyframes wholeFade{0%,100%{opacity:.18;filter:brightness(.6)}50%{opacity:1;filter:brightness(1.25)}}
@keyframes paletteFade{0%,100%{background:var(--c1)}33%{background:var(--c2)}66%{background:var(--c3)}}
@keyframes wholePalette{0%,32%{background:var(--c1)}33%,65%{background:var(--c2)}66%,100%{background:var(--c3)}}
@keyframes stripePalette{0%,100%{background:var(--c1);opacity:.3}34%{background:var(--c2);opacity:1}67%{background:var(--c3);opacity:1}}
@keyframes rainFall{0%{opacity:.15;filter:hue-rotate(0deg)}45%{opacity:1}100%{opacity:.18;filter:hue-rotate(360deg)}}
@keyframes snakeTrail{0%,70%{opacity:.06;transform:translate(-50%,-50%) scale(.65)}76%,88%{opacity:1;transform:translate(-50%,-50%) scale(1.22)}100%{opacity:.08}}
@keyframes antTrail{0%,82%{opacity:.04}86%,92%{opacity:1;transform:translate(-50%,-50%) scale(1.34)}100%{opacity:.05}}
@keyframes moonStars{0%,80%,100%{opacity:.14}86%{opacity:1;transform:translate(-50%,-50%) scale(1.45)}92%{opacity:.4}}
@keyframes collide{0%,100%{opacity:.08;transform:translate(-50%,-50%) scale(.7)}50%{opacity:1;transform:translate(-50%,-50%) scale(1.25)}}
@keyframes fire{0%{opacity:.22;filter:hue-rotate(-22deg) brightness(.65);transform:translate(-50%,-50%) scale(.8)}55%{opacity:1;filter:hue-rotate(12deg) brightness(1.35);transform:translate(-50%,-50%) scale(1.15)}100%{opacity:.55;filter:hue-rotate(-8deg)}}
@keyframes randomBreath{0%,100%{opacity:.1;transform:translate(-50%,-50%) scale(.75)}50%{opacity:1;transform:translate(-50%,-50%) scale(1.18)}}
@keyframes rowWave{0%,100%{opacity:.08;filter:brightness(.55)}50%{opacity:1;filter:brightness(1.45);transform:translate(-50%,-50%) scale(1.18)}}
@keyframes flagWave{0%,100%{transform:translate(-50%,-50%) translateX(-2px);filter:brightness(.78)}50%{transform:translate(-50%,-50%) translateX(4px);filter:brightness(1.3)}}
@keyframes heapUp{0%,30%{opacity:.05}48%,76%{opacity:1}100%{opacity:.12}}
@keyframes verticalWave{0%,100%{opacity:.1;transform:translate(-50%,-50%) scale(.8)}50%{opacity:1;transform:translate(-50%,-50%) scale(1.2);filter:brightness(1.4)}}
@media(max-width:430px){.visual-shell{grid-template-columns:minmax(0,1fr) 92px}.visual{min-height:330px}.effect-side{padding:10px 8px}.effect-side strong{font-size:12px}.tree i{width:7px;height:7px}}
@media(prefers-reduced-motion:reduce){.tree i{animation:none!important}}`;
