
import { useEffect, useState } from 'react'
import { Progress, Table, Tag, Typography, Space, Button, Modal, Empty, message, Alert } from 'antd'
import { ReloadOutlined, PlayCircleOutlined, DownloadOutlined } from '@ant-design/icons'
import { listJobs } from '../api'
import type { Job } from '../types'

const { Title, Text } = Typography

/** 从 result 中拼出一个浏览器可访问的视频 URL。
 *  后端 result.video_url 形如 "/static/outputs/<project_id>/m2a_xxx/final.mp4"。
 *  通过 nginx 反代或直连后端，当前 origin 都能正确访问到。
 */
function pickVideoUrl(job: Job): string {
  const r: any = job.result || {}
  if (r.video_url && typeof r.video_url === 'string') return r.video_url
  // 兜底：有些老任务只存了绝对 video_path，前端没法用；交互层给个提示
  return ''
}

export default function JobsPage() {
  const [list, setList] = useState<Job[]>([])
  const [preview, setPreview] = useState<{ visible: boolean; url: string; title: string; codec: string; compatible: boolean }>({
    visible: false, url: '', title: '', codec: '', compatible: true,
  })

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
    // 后端如果没传 browser_compatible 字段，默认 true；如果传了 false 一定要尊重它
    const compatible: boolean = r.browser_compatible !== false
    setPreview({
      visible: true,
      url,
      title: `${job.type} · ${job.id.slice(0, 8)}`,
      codec,
      compatible,
    })
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
                        : t === 'episode_render' ? <Tag color="blue">剧集渲染</Tag>
                        : <Tag>{t}</Tag>,
          },
          {
            title: '状态', dataIndex: 'status',
            render: (s) => {
              const color: any = { pending: 'default', running: 'processing', success: 'success', failed: 'error' }
              return <Tag color={color[s]}>{s}</Tag>
            },
          },
          {
            title: '进度',
            render: (_, r) => (
              <Progress percent={Math.round((r.progress || 0) * 100)} size="small"
                        status={r.status === 'failed' ? 'exception' : r.status === 'success' ? 'success' : 'active'} />
            ),
          },
          { title: '阶段', dataIndex: 'stage' },
          { title: '消息', dataIndex: 'message', ellipsis: true },
          {
            title: '时间', dataIndex: 'updated_at',
            render: (t) => new Date(t).toLocaleTimeString(),
          },
          {
            title: '操作', key: 'actions', width: 180, fixed: 'right',
            render: (_, job) => {
              const url = pickVideoUrl(job)
              const canPlay = job.status === 'success' && !!url
              return (
                <Space size="small">
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
                      // 用 a 标签触发下载
                      const a = document.createElement('a')
                      a.href = url
                      a.download = ''
                      a.target = '_blank'
                      document.body.appendChild(a)
                      a.click()
                      document.body.removeChild(a)
                    }}
                  >
                    下载
                  </Button>
                </Space>
              )
            },
          },
        ]}
        scroll={{ x: 1100 }}
      />

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
    </div>
  )
}
