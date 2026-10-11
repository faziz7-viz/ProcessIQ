// Progressive enhancement only: never writes input.value or dispatches an input event.
export default function({data}) {
  const root = document.querySelector('.st-key-interview-answer');
  if (!root) return;
  const input = root.querySelector('input');
  if (!input) return;
  const media = window.matchMedia('(prefers-reduced-motion: reduce)');
  let index = 0, interval, fade;
  const hints = data.hints;
  const stop = () => {clearInterval(interval); clearTimeout(fade); input.classList.remove('pi-hint-changing');};
  const refresh = () => {
    stop();
    if (input.value) {input.placeholder = ''; return;}
    input.placeholder = hints[index];
    if (media.matches || hints.length < 2) return;
    interval = setInterval(() => {
      if (!input.isConnected || input.value || document.hidden) {refresh();return;}
      input.classList.add('pi-hint-changing');
      fade = setTimeout(() => {
        if (!input.value) {index = (index + 1) % hints.length; input.placeholder = hints[index];}
        input.classList.remove('pi-hint-changing');
      }, 170);
    }, 4800);
  };
  input.addEventListener('input', refresh);
  media.addEventListener('change', refresh);
  refresh();
  return () => {stop(); input.removeEventListener('input',refresh); media.removeEventListener('change',refresh);};
}
