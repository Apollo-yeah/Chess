import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { fetchHealth, fetchServerStatus } from '../utils/apiUtils.js';
import './StatusPage.css';

const REFRESH_MS = 5000;

const LEVEL_TEXT = {
  ok: '稳定',
  warn: '留意',
  crit: '不稳定',
  skip: '不适用',
};

const VERDICT_TEXT = {
  stable: '稳定',
  watch: '留意',
  unstable: '不稳定',
};

const GROUP_TEXT = {
  host: '主机',
  nginx: 'Nginx',
  app: '应用',
};

function formatBytes(value) {
  if (value == null || Number.isNaN(Number(value))) return '—';
  let amount = Number(value);
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let index = 0;
  while (amount >= 1024 && index < units.length - 1) {
    amount /= 1024;
    index += 1;
  }
  if (index === 0) return `${Math.round(amount)} B`;
  return `${amount.toFixed(1)} ${units[index]}`;
}

function formatDuration(seconds) {
  if (seconds == null || Number.isNaN(Number(seconds))) return '—';
  const value = Math.max(0, Math.floor(Number(seconds)));
  const days = Math.floor(value / 86400);
  const hours = Math.floor((value % 86400) / 3600);
  const minutes = Math.floor((value % 3600) / 60);
  if (days) return `${days}天 ${hours}小时`;
  if (hours) return `${hours}小时 ${minutes}分`;
  if (minutes) return `${minutes}分`;
  return `${value}秒`;
}

function formatTime(iso) {
  if (!iso) return '—';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString('zh-CN', { hour12: false });
}

function text(value) {
  if (value == null || value === '') return '—';
  return String(value);
}

function percentText(value) {
  if (value == null || Number.isNaN(Number(value))) return '—';
  return `${Math.round(Number(value))}%`;
}

function levelOf(checks, id) {
  return (checks || []).find((item) => item.id === id)?.level || 'ok';
}

function Meter({ percent, level }) {
  const safe = Number.isFinite(Number(percent))
    ? Math.max(0, Math.min(100, Number(percent)))
    : 0;
  return (
    <div className="meter" role="meter" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(safe)}>
      <span className={`meter__fill meter__fill--${level}`} style={{ width: `${safe}%` }} />
    </div>
  );
}

function Row({ label, children }) {
  return (
    <div className="kv">
      <dt>{label}</dt>
      <dd>{children}</dd>
    </div>
  );
}

export default function StatusPage() {
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [probe, setProbe] = useState(null);
  const [probing, setProbing] = useState(false);

  useEffect(() => {
    const previousTitle = document.title;
    document.title = '服务状态 · z_chess';
    return () => {
      document.title = previousTitle;
    };
  }, []);

  useEffect(() => {
    let alive = true;

    const load = async () => {
      if (document.hidden) return;
      try {
        const payload = await fetchServerStatus();
        if (!alive) return;
        setData(payload);
        setError('');
      } catch (err) {
        if (!alive) return;
        setError(err.message || '无法获取状态');
      } finally {
        if (alive) setLoading(false);
      }
    };

    load();
    const timer = window.setInterval(load, REFRESH_MS);
    const onVisible = () => {
      if (!document.hidden) load();
    };
    document.addEventListener('visibilitychange', onVisible);
    return () => {
      alive = false;
      window.clearInterval(timer);
      document.removeEventListener('visibilitychange', onVisible);
    };
  }, []);

  const refresh = async () => {
    setLoading(true);
    try {
      const payload = await fetchServerStatus();
      setData(payload);
      setError('');
    } catch (err) {
      setError(err.message || '无法获取状态');
    } finally {
      setLoading(false);
    }
  };

  const probeEngine = async () => {
    setProbing(true);
    try {
      const health = await fetchHealth();
      setProbe(health);
    } catch (err) {
      setProbe({ status: 'error', error: err.message || '探测失败' });
    } finally {
      setProbing(false);
    }
  };

  const verdict = data?.verdict;
  const checks = data?.checks || [];
  const host = data?.host || {};
  const process = data?.process || {};
  const nginx = data?.nginx || {};
  const app = data?.app || {};
  const memory = host.memory || {};
  const connections = nginx.connections;
  const logs = nginx.logs;
  const engine = app.engine || {};
  const jobs = app.jobs || {};
  const games = app.games || {};
  const realtime = app.realtime || {};
  const cache = app.analysis_cache || {};
  const config = app.config || {};
  const storage = app.storage || {};

  return (
    <main className="status-page">
      <header className="status-header">
        <div>
          <p className="status-kicker">z_chess</p>
          <h1>服务状态</h1>
          <p className="status-lead">
            查看这台机器、Nginx 和棋局服务的参数。页面每 5 秒采样一次，并按每张卡片上的阈值判断是否稳定。
          </p>
        </div>
        <div className="status-header__actions">
          <Link to="/" className="status-btn status-btn--ghost">返回对弈</Link>
          <button type="button" className="status-btn" onClick={refresh} disabled={loading}>
            {loading ? '采集中…' : '立即刷新'}
          </button>
        </div>
      </header>

      {error && (
        <p className="status-banner status-banner--crit" role="alert">
          最近一次采集失败：{error}
          {data ? ' 下面仍是上一份成功的结果。' : ''}
        </p>
      )}

      {!data && loading && <p className="status-lead">正在读取服务器参数…</p>}

      {data && (
        <>
          <section className={`verdict verdict--${verdict?.level || 'watch'}`}>
            <div>
              <p className="verdict__label">综合判定</p>
              <h2>{VERDICT_TEXT[verdict?.level] || '未知'}</h2>
              <p>{verdict?.summary}</p>
            </div>
            <dl className="verdict__meta">
              <div>
                <dt>稳定</dt>
                <dd>{verdict?.counts?.ok ?? 0}</dd>
              </div>
              <div>
                <dt>留意</dt>
                <dd>{verdict?.counts?.warn ?? 0}</dd>
              </div>
              <div>
                <dt>不稳定</dt>
                <dd>{verdict?.counts?.crit ?? 0}</dd>
              </div>
              <div>
                <dt>采样</dt>
                <dd>{formatTime(data.collected_at)}</dd>
              </div>
            </dl>
          </section>

          <section className="check-grid" aria-label="稳定性指标">
            {checks.map((item) => (
              <article key={item.id} className={`check check--${item.level}`}>
                <header>
                  <span>{GROUP_TEXT[item.group] || item.group}</span>
                  <strong className={`pill pill--${item.level}`}>{LEVEL_TEXT[item.level] || item.level}</strong>
                </header>
                <h3>{item.label}</h3>
                <p className="check__value">{item.value}</p>
                <p className="check__detail">{item.detail}</p>
                <p className="check__rule">{item.rule}</p>
              </article>
            ))}
          </section>

          <section className="panel">
            <header className="panel__header">
              <h2>Nginx</h2>
              <p>{nginx.version || '未读到版本'}</p>
            </header>
            <dl className="kv-list">
              <Row label="监听">{text(nginx.config?.listen)}</Row>
              <Row label="worker 进程数">{text(nginx.config?.worker_processes)}</Row>
              <Row label="worker 连接上限">{text(nginx.config?.worker_connections)}</Row>
              <Row label="gzip">{text(nginx.config?.gzip)}</Row>
              <Row label="请求体上限">{text(nginx.config?.client_max_body_size)}</Row>
              <Row label="版本号回显">{text(nginx.config?.server_tokens)}</Row>
              <Row label="主进程">{nginx.master_pid ? `${nginx.master_pid}${nginx.master_alive ? ' · 存活' : ' · 已退出'}` : '—'}</Row>
              <Row label="worker 数量">{text(nginx.workers)}</Row>
              <Row label="状态接口">{text(nginx.status_url)}</Row>
            </dl>
            {connections ? (
              <div className="stat-grid">
                <Stat label="活跃连接" value={connections.active} />
                <Stat label="正在读取" value={connections.reading} />
                <Stat label="正在发送" value={connections.writing} />
                <Stat label="空闲等待" value={connections.waiting} />
                <Stat label="累计接受" value={connections.accepts} />
                <Stat label="累计处理" value={connections.handled} />
                <Stat label="累计请求" value={connections.requests} />
                <Stat label="请求/秒" value={connections.requests_per_sec ?? '—'} />
              </div>
            ) : (
              <p className="panel__note">当前没有 Nginx 连接计数。本机部署后，状态接口在 127.0.0.1:8157。</p>
            )}
            {logs && (
              <dl className="kv-list">
                <Row label="近 15 分钟请求">{text(logs.http_total_recent)}</Row>
                <Row label="近 15 分钟 5xx">{text(logs.http_5xx_recent)}</Row>
                <Row label="近 15 分钟错误">{text(logs.error_recent)}</Row>
                <Row label="近 15 分钟警告">{text(logs.warn_recent)}</Row>
              </dl>
            )}
            {logs?.latest_error && <p className="log-line">{logs.latest_error}</p>}
          </section>

          <div className="panel-grid">
            <section className="panel">
              <header className="panel__header">
                <h2>主机</h2>
                <p>{text(host.hostname)}</p>
              </header>
              <dl className="kv-list">
                <Row label="系统">{[host.system, host.release, host.machine].filter(Boolean).join(' ') || '—'}</Row>
                <Row label="Python">{text(host.python)}</Row>
                <Row label="已运行">{formatDuration(host.uptime_seconds)}</Row>
                <Row label="CPU">{host.cpu_percent == null ? '—' : `${host.cpu_percent}% · ${text(host.cpu_count)} 核`}</Row>
                <Row label="负载">{(host.load || []).length ? host.load.map((item) => item.toFixed(2)).join(' / ') : '—'}</Row>
              </dl>
              <div className="meter-block">
                <div className="meter-block__label">
                  <span>内存</span>
                  <span>{percentText(memory.percent)} · {formatBytes(memory.used)} / {formatBytes(memory.total)}</span>
                </div>
                <Meter percent={memory.percent} level={levelOf(checks, 'memory')} />
              </div>
              <div className="meter-block">
                <div className="meter-block__label">
                  <span>交换分区</span>
                  <span>
                    {memory.swap_total
                      ? `${percentText(memory.swap_percent)} · ${formatBytes(memory.swap_used)} / ${formatBytes(memory.swap_total)}`
                      : '未启用'}
                  </span>
                </div>
                <Meter percent={memory.swap_percent || 0} level={levelOf(checks, 'swap')} />
              </div>
              {(host.disks || []).map((disk, index) => (
                <div className="meter-block" key={disk.path}>
                  <div className="meter-block__label">
                    <span>{disk.label}</span>
                    <span>{percentText(disk.percent)} · 剩余 {formatBytes(disk.free)}</span>
                  </div>
                  <Meter percent={disk.percent} level={levelOf(checks, `disk-${index}`)} />
                  <p className="meter-block__path">{disk.path}</p>
                </div>
              ))}
              <h3 className="panel__sub">API 进程</h3>
              <dl className="kv-list">
                <Row label="PID">{text(process.pid)}</Row>
                <Row label="内存">{formatBytes(process.rss)}</Row>
                <Row label="线程">{text(process.threads)}</Row>
                <Row label="文件描述符">{process.open_fds != null ? `${process.open_fds} / ${text(process.nofile_soft)}` : '—'}</Row>
                <Row label="进程已运行">{formatDuration(process.uptime_seconds)}</Row>
                <Row label="本次采集">{data.duration_ms != null ? `${data.duration_ms} ms` : '—'}</Row>
              </dl>
            </section>

            <section className="panel">
              <header className="panel__header">
                <h2>棋局服务</h2>
                <p>{text(app.listen)}</p>
              </header>
              <dl className="kv-list">
                <Row label="Stockfish">{engine.available ? '可执行文件就绪' : '不可用'}</Row>
                <Row label="引擎路径">{text(engine.path)}</Row>
                <Row label="引擎池">{`${text(engine.instances)} 已创建 / ${text(engine.pool_size)} 上限 · 空闲 ${text(engine.idle)}`}</Row>
                <Row label="Hash / 线程">{`${text(config.engine_hash_mb)} MB / ${text(config.engine_threads)}`}</Row>
                <Row label="分析深度">{`局面 ${text(config.analysis_depth)} · 推送 ${text(config.broadcast_depth)} · 棋谱 ${text(config.pgn_depth)}`}</Row>
                <Row label="分析任务">{`${text(jobs.active)} 进行中 / 上限 ${text(jobs.max)} · 共 ${text(jobs.total)}`}</Row>
                <Row label="对局缓存">{`${text(games.cached)} / ${text(games.max_cached)} · 锁定 ${text(games.locked)}`}</Row>
                <Row label="实时连接">{`${text(realtime.subscribers)} 个订阅 · ${text(realtime.games)} 局 · ${text(realtime.analysis_tasks)} 个分析`}</Row>
                <Row label="分析缓存">
                  {`${text(cache.size)} / ${text(cache.maxsize)} · 命中率 ${cache.hit_rate == null ? '—' : `${Math.round(cache.hit_rate * 1000) / 10}%`}`}
                </Row>
                <Row label="对局目录">{text(storage.data_dir)}</Row>
                <Row label="棋谱目录">{text(storage.pgn_dir)}</Row>
              </dl>
              <div className="probe">
                <button type="button" className="status-btn" onClick={probeEngine} disabled={probing}>
                  {probing ? '正在探测…' : '探测引擎'}
                </button>
                <p>
                  自动刷新只检查引擎文件是否存在，避免每 5 秒占用 Stockfish。需要确认引擎能算出棋时再点探测。
                </p>
                {probe && (
                  <p className={`probe__result probe__result--${probe.status === 'ok' ? 'ok' : 'crit'}`}>
                    {probe.status === 'ok'
                      ? '引擎响应正常'
                      : (probe.error || probe.engine?.error || '引擎没有通过探测')}
                  </p>
                )}
              </div>
            </section>
          </div>
        </>
      )}
    </main>
  );
}

function Stat({ label, value }) {
  return (
    <div className="stat">
      <span className="stat__value">{text(value)}</span>
      <span className="stat__label">{label}</span>
    </div>
  );
}
