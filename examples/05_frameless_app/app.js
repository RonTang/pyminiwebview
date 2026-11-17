const byId = id => document.getElementById(id);
const bridgeResult = byId('bridge-result');
const syncStatus = byId('sync-status');
const syncBar = byId('sync-bar');
const syncPercent = byId('sync-percent');

function errorText(error) {
  return error && error.error ? `${error.error.type}: ${error.error.message}` : String(error);
}

window.app = {
  setMaximized(maximized) {
    const button = byId('btn-max');
    button.textContent = maximized ? '❐' : '□';
    button.title = maximized ? '还原' : '最大化';
    button.setAttribute('aria-label', button.title);
  },
  updateTask(value, message) {
    syncBar.style.width = `${value}%`;
    syncPercent.textContent = `${value}%`;
    syncStatus.textContent = message;
  },
  taskFinished(completed) {
    const value = completed ? 100 : 0;
    window.app.updateTask(value, completed ? '同步完成：页面更新始终在 UI 线程执行。' : '同步已取消，可以重新开始。');
  }
};

const windowButtons = [...document.querySelectorAll('.window-button')];
function clearWindowButtonHover() {
  windowButtons.forEach(button => button.classList.remove('hover'));
}
document.addEventListener('pointermove', event => {
  const hovered = event.target.closest('.window-button');
  windowButtons.forEach(button => button.classList.toggle('hover', button === hovered));
});
document.addEventListener('pointerleave', clearWindowButtonHover);
window.addEventListener('blur', clearWindowButtonHover);

byId('btn-min').addEventListener('click', () => {
  clearWindowButtonHover();
  __window_minimize();
});
byId('btn-max').addEventListener('click', () => __window_toggle_maximize());
byId('btn-close').addEventListener('click', () => __window_close());
byId('titlebar').addEventListener('mousedown', event => {
  if (event.button === 0 && !event.target.closest('button')) __window_start_move();
});

byId('bridge-button').addEventListener('click', async () => {
  bridgeResult.textContent = '正在等待 Python 返回…';
  try {
    const data = await get_dashboard_data();
    byId('total-value').textContent = data.total;
    byId('checked-at').textContent = `Python 校验 · ${data.checkedAt}`;
    bridgeResult.textContent = data.message;
  } catch (error) {
    bridgeResult.textContent = errorText(error);
  }
});

byId('sync-button').addEventListener('click', async () => {
  try {
    const result = await start_sync();
    syncStatus.textContent = result.message;
  } catch (error) {
    syncStatus.textContent = errorText(error);
  }
});

byId('cancel-button').addEventListener('click', async () => {
  try {
    const result = await cancel_sync();
    syncStatus.textContent = result.message;
  } catch (error) {
    syncStatus.textContent = errorText(error);
  }
});
