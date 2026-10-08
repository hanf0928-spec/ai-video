
import { useEffect, useState } from 'react'
import {
  Button, Card, Empty, Form, Input, Modal, Select, Space, Tabs, Typography, message,
} from 'antd'
import { PlusOutlined } from '@ant-design/icons'
import {
  listProjects, listCharacters, createCharacter, listScenes, createScene,
} from '../api'
import type { Character, Project } from '../types'

const { Title, Text } = Typography

export default function CharactersPage() {
  const [projects, setProjects] = useState<Project[]>([])
  const [pid, setPid] = useState<string>()
  const [chars, setChars] = useState<Character[]>([])
  const [scenes, setScenes] = useState<any[]>([])
  const [open, setOpen] = useState<'character' | 'scene' | null>(null)
  const [form] = Form.useForm()

  useEffect(() => { listProjects().then((ps) => { setProjects(ps); if (ps[0]) setPid(ps[0].id) }) }, [])
  useEffect(() => {
    if (!pid) return
    listCharacters(pid).then(setChars)
    listScenes(pid).then(setScenes)
  }, [pid])

  const onCreate = async () => {
    const v = await form.validateFields()
    if (open === 'character') {
      await createCharacter({ project_id: pid, ...v, reference_images: [] })
      message.success('角色已创建')
      setChars(await listCharacters(pid!))
    } else {
      await createScene({ project_id: pid, ...v, reference_images: [] })
      message.success('场景已创建')
      setScenes(await listScenes(pid!))
    }
    setOpen(null); form.resetFields()
  }

  return (
    <div>
      <Space style={{ marginBottom: 16 }}>
        <Title level={3} style={{ color: '#fff', margin: 0 }}>👥 角色与场景</Title>
        <Select
          style={{ width: 240 }}
          placeholder="选择项目"
          value={pid}
          onChange={setPid}
          options={projects.map((p) => ({ value: p.id, label: p.name }))}
        />
      </Space>

      <Tabs
        items={[
          {
            key: 'ch', label: '角色',
            children: (
              <>
                <Button type="primary" icon={<PlusOutlined />} onClick={() => setOpen('character')} style={{ marginBottom: 12 }}>
                  新建角色
                </Button>
                {chars.length === 0 ? <Empty /> : (
                  <div className="card-grid">
                    {chars.map((c) => (
                      <Card key={c.id} size="small" title={c.name}>
                        <Text type="secondary">{c.description || '-'}</Text>
                        <p>Voice: {c.voice_id || '未绑定'}</p>
                        <p>LoRA: {c.lora_path || '未绑定'}</p>
                      </Card>
                    ))}
                  </div>
                )}
              </>
            ),
          },
          {
            key: 'sc', label: '场景',
            children: (
              <>
                <Button type="primary" icon={<PlusOutlined />} onClick={() => setOpen('scene')} style={{ marginBottom: 12 }}>
                  新建场景
                </Button>
                {scenes.length === 0 ? <Empty /> : (
                  <div className="card-grid">
                    {scenes.map((s) => (
                      <Card key={s.id} size="small" title={s.name}>
                        <Text type="secondary">{s.description || '-'}</Text>
                        <p>Prompt: {s.style_prompt || '-'}</p>
                      </Card>
                    ))}
                  </div>
                )}
              </>
            ),
          },
        ]}
      />

      <Modal
        title={open === 'character' ? '新建角色' : '新建场景'}
        open={!!open} onOk={onCreate} onCancel={() => setOpen(null)}
      >
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="名称" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea rows={3} />
          </Form.Item>
          {open === 'character' && (
            <Form.Item name="voice_id" label="音色 ID">
              <Input placeholder="例：female-shaonv" />
            </Form.Item>
          )}
          {open === 'scene' && (
            <Form.Item name="style_prompt" label="风格 Prompt">
              <Input.TextArea rows={2} />
            </Form.Item>
          )}
        </Form>
      </Modal>
    </div>
  )
}
