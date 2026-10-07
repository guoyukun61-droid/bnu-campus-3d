"""Replace named primitives without re-exporting any unrelated GLB geometry."""
import copy, json, struct

def unpack_glb(raw):
    size=struct.unpack_from('<I',raw,12)[0]
    return json.loads(raw[20:20+size]),raw[28+size:]

def patch_meshes(original,replacement,names):
    doc,binary=unpack_glb(original);other,new_binary=unpack_glb(replacement)
    binary=bytearray(binary);accessors={};views={}
    def move_accessor(index):
        if index in accessors:return accessors[index]
        a=copy.deepcopy(other['accessors'][index]);vi=a['bufferView']
        if vi not in views:
            v=copy.deepcopy(other['bufferViews'][vi]);start=v.get('byteOffset',0)
            binary.extend(b'\0'*((-len(binary))%4));v['byteOffset']=len(binary);v['buffer']=0
            binary.extend(new_binary[start:start+v['byteLength']])
            views[vi]=len(doc['bufferViews']);doc['bufferViews'].append(v)
        a['bufferView']=views[vi];accessors[index]=len(doc['accessors']);doc['accessors'].append(a)
        return accessors[index]
    source={n['name']:n for n in other['nodes'] if 'mesh'in n}
    materials={m.get('name'):i for i,m in enumerate(doc['materials'])}
    for node in doc['nodes']:
        if node.get('name') not in names:continue
        new=copy.deepcopy(other['meshes'][source[node['name']]['mesh']])
        for p in new['primitives']:
            p['indices']=move_accessor(p['indices'])
            p['attributes']={k:move_accessor(v) for k,v in p['attributes'].items()}
            if 'material'in p:p['material']=materials[other['materials'][p['material']]['name']]
        doc['meshes'][node['mesh']]=new
    doc['buffers'][0]['byteLength']=len(binary)
    raw=json.dumps(doc,separators=(',',':'),ensure_ascii=False).encode();raw+=b' '*((-len(raw))%4)
    binary.extend(b'\0'*((-len(binary))%4))
    return struct.pack('<III',0x46546c67,2,28+len(raw)+len(binary))+struct.pack('<II',len(raw),0x4e4f534a)+raw+struct.pack('<II',len(binary),0x004e4942)+binary
