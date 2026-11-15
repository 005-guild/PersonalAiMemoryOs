const fixture = {"schema_version": 1, "items": [{"url": "https://www.zhihu.com/question/12/answer/34", "title": "原生保存验收合成资料", "content": "仅用于隔离文件对话框验收，不包含个人资料。"}]};
function attachFixture() {
  const input = document.querySelector('[data-testid="import-file"]');
  if (!input || document.querySelector('[data-testid="native-fixture-load"]')) return;
  const button = document.createElement('button');
  button.type = 'button'; button.className = 'btn';
  button.dataset.testid = 'native-fixture-load';
  button.textContent = '载入验收用合成文件';
  button.addEventListener('click', () => {
    const transfer = new DataTransfer();
    transfer.items.add(new File([JSON.stringify(fixture)], 'native-fixture.json', {type:'application/json'}));
    input.files = transfer.files;
    input.dispatchEvent(new Event('change', {bubbles:true}));
    button.disabled = true;
  });
  input.after(button);
}
new MutationObserver(attachFixture).observe(document.body, {childList:true, subtree:true});
attachFixture();
