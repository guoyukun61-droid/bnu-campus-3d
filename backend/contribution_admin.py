"""Owner-operated, offline credential/backup tool. Never invoked by the web UI."""
import argparse
import getpass
import hashlib
import secrets
import zipfile
from pathlib import Path
from .storage import ROOT, read, write, now


def main():
    parser=argparse.ArgumentParser(description="仅在获用户明确授权后运行；先停止协作服务。")
    parser.add_argument("action",choices=["add","revoke","backup"])
    parser.add_argument("--id")
    parser.add_argument("--name")
    parser.add_argument("--role",choices=["member","admin"],default="member")
    parser.add_argument("--output",help="备份ZIP的明确路径，必须不存在")
    args=parser.parse_args();directory=ROOT/"data/life/contributions"
    if args.action=="backup":
        if not args.output:parser.error("须指定 --output")
        output=Path(args.output).resolve()
        if output.is_relative_to(directory.resolve()):parser.error("备份不能放入源目录")
        if not directory.exists():parser.error("尚无协作数据")
        with zipfile.ZipFile(output,"x",zipfile.ZIP_DEFLATED) as archive:
            for path in directory.rglob("*"):
                if path.is_file() and path.name not in {"writer.lock","members.json"}:
                    archive.write(path,path.relative_to(directory).as_posix())
        print("备份完成（不含成员凭证摘要）。")
        return
    if not args.id or not args.id.replace("-","").isalnum():parser.error("须指定字母数字成员ID")
    members=read(directory/"members.json",[])
    if args.action=="revoke":
        member=next((u for u in members if u["id"]==args.id),None)
        if member is None:parser.error("成员不存在")
        member["active"]=False
    else:
        if not args.name:parser.error("须指定显示名称")
        if any(u["id"]==args.id for u in members):parser.error("成员ID已存在；不覆盖原凭证")
        # Owner chooses a random credential outside process arguments and logs.
        token=getpass.getpass("粘贴单独生成的高强度邀请凭证（至少32字符，不回显）：")
        if len(token)<32:parser.error("凭证至少32字符")
        members.append(dict(id=args.id,name=args.name,role=args.role,active=True,token_hash=hashlib.sha256(token.encode()).hexdigest(),created_at=now()))
    write(directory/"members.json",members)
    print("成员状态已保存；未输出凭证。")


if __name__=="__main__":main()
