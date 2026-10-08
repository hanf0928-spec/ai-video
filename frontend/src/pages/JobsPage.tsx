
import { useEffect, useState } from 'react'
import { Progress, Table, Tag, Typography, Space, Button } from 'antd'
import { ReloadOutlined } from '@ant-design/icons'
import { listJobs } from '../api'
import type { Job } from '../types'

const { Title } = Typography

export default function JobsPage() {
  const [list, setList] = useState<Job[]>([])

  const load = async () => setList(await listJobs())
  useEffect(() => {
    load()
    const t = setInterval(load, 3000)
    return () => clearInterval(t)
  }, [])

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
        ]}
      />
    </div>
  )
}
