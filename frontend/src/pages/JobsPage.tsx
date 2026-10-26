
import { useEffect, useState } from 'react'
import { Progress, Table, Tag, Typography, Space, Button, Modal, Empty, message, Alert, Descriptions, Tabs } from 'antd'
import { ReloadOutlined, PlayCircleOutlined, DownloadOutlined, StopOutlined, FileSearchOutlined } from '@ant-design/icons'
import { listJobs, stopJob } from '../api'
import type { Job } from '../types'

const { Title, Text, Paragraph } = Typography

/** 从 result 中拼出一个浏览器可访问的视频 URL（漫画转漫剧 / 剧集渲染）。
 *  后端 result.video_url 形如 "/static/outputs/<project_id>/m2a_xxx/final.mp4"。
 */
function pickVideoUrl(job: Job): string {
  const r: any = job.result || {}
  if (r.video_url && typeof r.video_url === 'string') return r.video_url
  return ''
}

/** 漫画拆解任务：从 result 里取可查看的"报告"数据（整个 result 就是报告）。
 *  有 storyboard / characters / script 中任一字段，即视为有效报告。
 */
function hasAnalysisReport(job: Job): boolean {
  if (job.type !== 'manga_analyze' && job.type !== 'novel_analyze') return false
  const r: any = job.result || {}
  return !!(r.storyboard || r.characters || r.script)
}

export default function JobsPage() {
  const [list, setList] = useState<Job[]>([])
  const [preview, setPreview] = useState<{ visible: boolean; url: string; title: string; codec: string; compatible: boolean }>({
    visible: false, url: '', title: '', codec: '', compatible: true,
  })
  const [reportJob, setReportJob] = useState<Job | null>(null)
  const [stopTarget, setStopTarget] = useState<Job | null>(null)
  const [stopping, setStopping] = useState(false)

  const load = async () => setList(await listJobs())
  useEffect(() => {
    load()
    const t = setInterval(load, 3000)
    return () => clearInterval(t)
  }, [])

  const openPreview = (job: Job) => {
    const url = pickVideoUrl(job)
    if (!url) {
      message.warning('该任务没有可播放的 video_url，可能是旧版产物。请重跑一次任务。')
      return
    }
    const r: any = job.result || {}
    const codec: string = (r.video_codec || '').toString()
    const compatible: boolean = r.browser_compatible !== false
    setPreview({
      visible: true,
      url,
      title: `${job.type} · ${job.id.slice(0, 8)}`,
      codec,
      compatible,
    })
  }

  const confirmStop = async () => {
    if (!stopTarget) return
    setStopping(true)
    try {
      await stopJob(stopTarget.id)
      message.success('已发送停止指令，任务将在下一个检查点终止')
      setStopTarget(null)
      await load()
    } catch (e: any) {
      message.error(e?.message || '停止失败')
    } finally {
      setStopping(false)
    }
  }

  const downloadReportJson = (job: Job) => {
    const name = `analysis-${job.id.slice(0, 8)}.json`
    const blob = new Blob([JSON.stringify(job.result, null, 2)], { type: 'application/json' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = name
    document.body.appendChild(a); a.click(); document.body.removeChild(a)
    URL.revokeObjectURL(a.href)
  }

  return (
    <div>
      <Space style={{ marginBottom: 12 }}>
        <Title level={3} style={{ color: '#fff', margin: 0 }}>📋 任务队列</Title>
        <Button icon={<ReloadOutlined />} onClick={load}>刷新</Button>
      </Space>
      <Table
        rowKey="id"
        dataSource={list}
        columns={[
          { title: 'ID', dataIndex: 'id', width: 120, ellipsis: true },
          {
            title: '类型', dataIndex: 'type',
            render: (t) => t === 'manga2anime' ? <Tag color="purple">漫画转漫剧</Tag>
                        : t === 'manga_analyze' ? <Tag color="cyan">漫画拆解</Tag>
                        : t === 'novel_analyze' ? <Tag color="geekblue">小说拆解</Tag>
                        : t === 'episode_render' ? <Tag color="blue">剧集渲染</Tag>
                        : <Tag>{t}</Tag>,
          },
          {
            title: '状态', dataIndex: 'status',
            render: (s) => {
              const color: any = {
                pending: 'default', running: 'processing', success: 'success',
                failed: 'error', cancelled: 'warning',
              }
              return <Tag color={color[s] || 'default'}>{s}</Tag>
            },
          },
          {
            title: '进度',
            render: (_, r) => (
              <Progress
                percent={Math.round((r.progress || 0) * 100)}
                size="small"
                status={
                  r.status === 'failed' ? 'exception'
                  : r.status === 'cancelled' ? 'exception'
                  : r.status === 'success' ? 'success'
                  : 'active'
                }
              />
            ),
          },
          { title: '阶段', dataIndex: 'stage' },
          { title: '消息', dataIndex: 'message', ellipsis: true },
          {
            title: '时间', dataIndex: 'updated_at',
            render: (t) => new Date(t).toLocaleTimeString(),
          },
          {
            title: '操作', key: 'actions', width: 260, fixed: 'right',
            render: (_, job) => {
              const videoUrl = pickVideoUrl(job)
              const isVideoType = job.type === 'manga2anime' || job.type === 'episode_render'
              const isAnalyzeType = job.type === 'manga_analyze' || job.type === 'novel_analyze'
              const canPlay = job.status === 'success' && !!videoUrl && isVideoType
              const canReport = job.status === 'success' && isAnalyzeType && hasAnalysisReport(job)
              const canStop = job.status === 'pending' || job.status === 'running'

              return (
                <Space size="small" wrap>
                  {/* 漫画转漫剧 / 剧集渲染 → 查看视频 */}
                  {isVideoType && (
                    <>
                      <Button
                        size="small"
                        type="primary"
                        icon={<PlayCircleOutlined />}
                        disabled={!canPlay}
                        onClick={() => openPreview(job)}
                      >
                        查看
                      </Button>
                      <Button
                        size="small"
                        icon={<DownloadOutlined />}
                        disabled={!canPlay}
                        onClick={() => {
                          const a = document.createElement('a')
                          a.href = videoUrl
                          a.download = ''
                          a.target = '_blank'
                          document.body.appendChild(a); a.click(); document.body.removeChild(a)
                        }}
                      >
                        下载
                      </Button>
                    </>
                  )}

                  {/* 漫画拆解 → 查看报告 / 下载 JSON */}
                  {isAnalyzeType && (
                    <>
                      <Button
                        size="small"
                        type="primary"
                        icon={<FileSearchOutlined />}
                        disabled={!canReport}
                        onClick={() => setReportJob(job)}
                      >
                        查看报告
                      </Button>
                      <Button
                        size="small"
                        icon={<DownloadOutlined />}
                        disabled={!canReport}
                        onClick={() => downloadReportJson(job)}
                      >
                        下载 JSON
                      </Button>
                    </>
                  )}

                  <Button
                    size="small"
                    danger
                    icon={<StopOutlined />}
                    disabled={!canStop}
                    onClick={() => setStopTarget(job)}
                  >
                    停止
                  </Button>
                </Space>
              )
            },
          },
        ]}
        scroll={{ x: 1200 }}
      />

      {/* 视频预览 Modal */}
      <Modal
        open={preview.visible}
        title={`🎬 ${preview.title}`}
        onCancel={() => setPreview({ visible: false, url: '', title: '', codec: '', compatible: true })}
        footer={null}
        width={900}
        destroyOnClose
      >
        {preview.url ? (
          <>
            {!preview.compatible && (
              <Alert
                type="warning"
                showIcon
                style={{ marginBottom: 12 }}
                message={`视频编码 ${preview.codec || 'unknown'} 浏览器不支持播放`}
                description={
                  <div>
                    <div>浏览器 &lt;video&gt; 只认 h264 / hevc / av1 / vp8 / vp9。当前视频用的是 <code>{preview.codec || 'mpeg4'}</code>，播放会黑屏。</div>
                    <div style={{ marginTop: 4 }}>
                      💡 <b>修复方法</b>：在服务器安装带 <code>libx264</code> 的 ffmpeg，然后重跑任务。
                      或者点下方 <b>⬇️ 下载</b> 用本地播放器（VLC / PotPlayer）打开。
                    </div>
                  </div>
                }
              />
            )}
            <video
              src={preview.url}
              controls
              autoPlay
              style={{ width: '100%', background: '#000', borderRadius: 4 }}
            />
            <div style={{ marginTop: 8 }}>
              <Text type="secondary" style={{ fontSize: 12 }}>视频地址：</Text>
              <Text copyable code style={{ fontSize: 12 }}>{preview.url}</Text>
              {preview.codec && (
                <>
                  <Text type="secondary" style={{ fontSize: 12, marginLeft: 12 }}>编码：</Text>
                  <Tag color={preview.compatible ? 'green' : 'orange'}>{preview.codec}</Tag>
                </>
              )}
            </div>
          </>
        ) : (
          <Empty description="没有可播放的视频" />
        )}
      </Modal>

      {/* 漫画拆解报告 Modal */}
      <Modal
        open={!!reportJob}
        title={`📑 漫画拆解报告 · ${reportJob?.id?.slice(0, 8)}`}
        onCancel={() => setReportJob(null)}
        footer={
          <Space>
            <Button icon={<DownloadOutlined />} onClick={() => reportJob && downloadReportJson(reportJob)}>
              下载 JSON
            </Button>
            <Button onClick={() => setReportJob(null)}>关闭</Button>
          </Space>
        }
        width={1000}
        destroyOnClose
      >
        {reportJob && <AnalysisReport result={reportJob.result || {}} />}
      </Modal>

      {/* 停止确认 Modal */}
      <Modal
        open={!!stopTarget}
        title="停止任务"
        okText="确认停止"
        okButtonProps={{ danger: true, loading: stopping }}
        onOk={confirmStop}
        onCancel={() => setStopTarget(null)}
      >
        <p>确定要停止任务 <code>{stopTarget?.id?.slice(0, 8)}</code> 吗？</p>
        <p style={{ color: '#999', fontSize: 12 }}>
          任务将在下一个进度检查点终止（正在进行的子步骤如图生视频、LLM 调用会被打断）。
        </p>
      </Modal>
    </div>
  )
}

// ---------- 漫画拆解报告组件（嵌入 Modal） ----------
function AnalysisReport({ result }: { result: Record<string, any> }) {
  if (!result || Object.keys(result).length === 0) {
    return <Empty description="报告为空" />
  }

  const chars: any[] = result.characters || []
  const acts: any[] = result.script?.acts || []
  const shots: any[] = result.storyboard || []
  const meta: any = result._meta || {}

  return (
    <>
      {result._fallback && (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 12 }}
          message="LLM 深度剖析未成功，当前为简化兜底版本"
          description={
            <>
              <div>请检查「🔧 模型配置 → 🧠 LLM」API Key，建议用非 reasoning 模型。</div>
              {result._fallback_reason && (
                <div style={{ marginTop: 6, color: '#faad14' }}>
                  <b>错误原因：</b>{result._fallback_reason}
                </div>
              )}
            </>
          }
        />
      )}

      <Tabs
        defaultActiveKey="overview"
        items={[
          {
            key: 'overview', label: '📖 概要',
            children: (
              <Descriptions column={1} bordered size="small">
                <Descriptions.Item label="标题">{result.title || '-'}</Descriptions.Item>
                <Descriptions.Item label="类型">{result.genre ? <Tag color="purple">{result.genre}</Tag> : '-'}</Descriptions.Item>
                <Descriptions.Item label="一句话概要">{result.summary || '-'}</Descriptions.Item>
                <Descriptions.Item label="整体氛围">{result.tone || '-'}</Descriptions.Item>
                <Descriptions.Item label="BGM 建议">{result.bgm_hint || '-'}</Descriptions.Item>
                <Descriptions.Item label="制作备注">{result.notes || '-'}</Descriptions.Item>
                <Descriptions.Item label="统计">
                  页 {meta.page_count ?? '?'} / 格 {meta.panel_count ?? '?'} / 角色聚类 {meta.character_cluster_count ?? '?'}
                </Descriptions.Item>
              </Descriptions>
            ),
          },
          {
            key: 'chars', label: `👥 角色 (${chars.length})`,
            children: chars.length === 0 ? <Empty /> : (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: 12 }}>
                {chars.map((c, i) => (
                  <div key={i} style={{ border: '1px solid #303030', padding: 12, borderRadius: 6 }}>
                    <Space><Text strong>{c.name}</Text>{c.role && <Tag color={c.role.includes('主') ? 'red' : 'blue'}>{c.role}</Tag>}</Space>
                    <div style={{ fontSize: 12, color: '#aaa', marginTop: 6, lineHeight: 1.8 }}>
                      {c.appearance && <div>👤 外貌：{c.appearance}</div>}
                      {c.costume && <div>👗 服装：{c.costume}</div>}
                      {c.personality && <div>💭 性格：{c.personality}</div>}
                      {c.voice_tone && <div>🎙 声线：{c.voice_tone}</div>}
                    </div>
                  </div>
                ))}
              </div>
            ),
          },
          {
            key: 'script', label: `🎭 剧本 (${acts.length})`,
            children: acts.length === 0 ? <Empty /> : (
              <Table
                size="small" pagination={false} rowKey={(_, i) => i!.toString()}
                dataSource={acts}
                columns={[
                  { title: '段落', dataIndex: 'name', width: 160, render: (v) => <Tag color="geekblue">{v}</Tag> },
                  { title: '分格范围', dataIndex: 'panels_range', width: 120, render: (v) => v ? `${v[0]} - ${v[1]}` : '-' },
                  { title: '剧情概要', dataIndex: 'summary' },
                ]}
              />
            ),
          },
          {
            key: 'shots', label: `🎬 分镜 (${shots.length})`,
            children: shots.length === 0 ? <Empty /> : (
              <div style={{ maxHeight: 500, overflow: 'auto' }}>
                {shots.map((s: any) => (
                  <div key={s.index} style={{ border: '1px solid #303030', padding: 10, borderRadius: 6, marginBottom: 10 }}>
                    <Space wrap style={{ marginBottom: 6 }}>
                      <Tag color="gold">#{s.index}</Tag>
                      {s.timecode && <Tag>{s.timecode}</Tag>}
                      {s.shot_type && <Tag color="purple">{s.shot_type}</Tag>}
                      {s.camera_motion && <Tag color="cyan">{s.camera_motion}</Tag>}
                      {s.environment?.time_of_day && <Tag color="blue">{s.environment.time_of_day}</Tag>}
                    </Space>
                    <div style={{ display: 'flex', gap: 10 }}>
                      {s.panel_image_url && (
                        <img
                          src={s.panel_image_url} alt=""
                          style={{ width: 140, flexShrink: 0, borderRadius: 4, background: '#000', objectFit: 'contain' }}
                        />
                      )}
                      <div style={{ flex: 1, fontSize: 12, lineHeight: 1.8 }}>
                        {s.environment && (
                          <div>🌍 {[s.environment.location, s.environment.weather, s.environment.lighting, s.environment.details].filter(Boolean).join(' / ')}</div>
                        )}
                        {(s.characters_in_shot || []).map((ch: any, i: number) => (
                          <div key={i}>
                            👤 <b>{ch.name}</b> {ch.costume && <>· 👗 {ch.costume}</>} {ch.action && <>· 🎬 {ch.action}</>} {ch.expression && <>· 😊 {ch.expression}</>} {ch.emotion && <Tag color="volcano">{ch.emotion}</Tag>}
                          </div>
                        ))}
                        {s.dialogue && <div>💬 {s.speaker ? `${s.speaker}：` : ''}{s.dialogue}</div>}
                        {s.sfx && <div>🔊 {s.sfx}</div>}
                        {s.image_prompt && <Paragraph type="secondary" style={{ fontSize: 11, margin: '4px 0 0' }} ellipsis={{ rows: 2, expandable: true }}>🖼 {s.image_prompt}</Paragraph>}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            ),
          },
          {
            key: 'raw', label: '🧾 原始 JSON',
            children: (
              <pre style={{ maxHeight: 500, overflow: 'auto', background: '#1a1a1a', color: '#ddd', padding: 12, borderRadius: 4, fontSize: 12 }}>
                {JSON.stringify(result, null, 2)}
              </pre>
            ),
          },
        ]}
      />
    </>
  )
}
