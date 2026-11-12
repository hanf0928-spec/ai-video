
import { useEffect, useState } from 'react'
import {
  Button, Card, Empty, Form, Input, Modal, Select, Space, Tabs, Typography, Upload, message,
} from 'antd'
import { PlusOutlined, UploadOutlined, UserOutlined } from '@ant-design/icons'
import {
  listProjects, listCharacters, createCharacter, listScenes, createScene,
  uploadCharacterAvatar,
} from '../api'
import type { Character, Project } from '../types'

const { Title, Text } = Typography

/** Character.reference_images[0] 存的是后端本地磁盘路径（如 .../data/uploads/{pid}/characters/{cid}.png），
 *  约定与 Shot.image_url 相同：前端按 "/uploads/" 切出相对路径拼 /static/uploads/ 访问。
 */
function avatarUrl(c: Character): string | null {
  const p = c.reference_images?.[0]
  if (!p) return null
  const idx = p.indexOf('/uploads/')
  if (idx === -1) return null
  return `/static${p.slice(idx)}`
}

export default function CharactersPage() {
  const [projects, setProjects] = useState<Project[]>([])
  const [pid, setPid] = useState<string>()
  const [chars, setChars] = useState<Character[]>([])
  const [scenes, setScenes] = useState<any[]>([])
  const [open, setOpen] = useState<'character' | 'scene' | null>(null)
  const [uploadingId, setUploadingId] = useState<string | null>(null)
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

  const onUploadAvatar = async (character: Character, file: File) => {
    setUploadingId(character.id)
    try {
      await uploadCharacterAvatar(character.id, file)
      message.success(`「${character.name}」形象图已更新`)
      setChars(await listCharacters(pid!))
    } catch (e: any) {
      message.error(e?.message || '上传失败')
    } finally {
      setUploadingId(null)
    }
    return false // 阻止 antd Upload 自动发起默认请求
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
                    {chars.map((c) => {
                      const avatar = avatarUrl(c)
                      return (
                      <Card key={c.id} size="small" title={c.name}>
                        <div style={{ display: 'flex', gap: 12, marginBottom: 8 }}>
                          <div
                            style={{
                              width: 72, height: 72, borderRadius: 6, flexShrink: 0,
                              background: '#1f1f1f', display: 'flex', alignItems: 'center', justifyContent: 'center',
                              overflow: 'hidden',
                            }}
                          >
                            {avatar ? (
                              <img src={avatar} alt={c.name} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                            ) : (
                              <UserOutlined style={{ fontSize: 28, color: '#555' }} />
                            )}
                          </div>
                          <div style={{ flex: 1 }}>
                            <Text type="secondary" style={{ fontSize: 12 }}>{c.description || '-'}</Text>
                            <p style={{ margin: '4px 0 0', fontSize: 12 }}>Voice: {c.voice_id || '未绑定'}</p>
                          </div>
                        </div>
                        <Upload
                          accept="image/png,image/jpeg,image/webp"
                          showUploadList={false}
                          beforeUpload={(file) => onUploadAvatar(c, file)}
                        >
                          <Button size="small" icon={<UploadOutlined />} loading={uploadingId === c.id} block>
                            {avatar ? '更换形象图' : '上传形象图（保持角色一致性）'}
                          </Button>
                        </Upload>
                      </Card>
                      )
                    })}
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
