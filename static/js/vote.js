// ▲/▼ sayfa yenilemeden (konu ve yorum). Framework yok: sayfadaki bütün form.vote'ları tek dinleyici yakalar.
// Form fetch ile gönderilir; CSRF jetonu formun gizli alanından (FormData) gider. Yanıt JSON değilse ya da
// hata varsa (oturum düşmüş, konu kapanmış…) form normal gönderilir: sunucu mesajı sayfada gösterir.
// JS kapalıysa bu dosya hiç çalışmaz, formlar bugünkü gibi çalışır.
document.addEventListener('submit', async (event) => {
  const form = event.target;
  const button = event.submitter;
  if (!form.matches('form.vote') || !button) return;
  event.preventDefault();
  if (form.dataset.busy) return;  // çift tık: önceki istek bitmeden ikincisi gitmesin
  const body = new FormData(form, button);  // basılan düğmenin value'su (1 ya da -1) dahil; kilitlemeden önce
  const buttons = form.querySelectorAll('button');
  form.dataset.busy = '1';
  buttons.forEach((b) => { b.disabled = true; });
  try {
    const response = await fetch(form.action, { method: 'POST', body, headers: { Accept: 'application/json' } });
    if (!response.ok || !response.headers.get('Content-Type')?.startsWith('application/json')) throw response;
    const { score, mine } = await response.json();
    form.querySelector('output').value = score;
    buttons.forEach((b) => b.setAttribute('aria-pressed', String(Number(b.value) === mine)));
  } catch {
    // form.submit() basılan düğmeyi göndermez; değeri gizli alanla eklenir
    form.append(Object.assign(document.createElement('input'), { type: 'hidden', name: 'value', value: button.value }));
    form.submit();
  } finally {
    delete form.dataset.busy;
    buttons.forEach((b) => { b.disabled = false; });
  }
});
