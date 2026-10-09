"""Local interactive provisioning; never accept passwords in arguments or print them."""
import argparse
import getpass
import sys
from backend.accounts import AccountStore, AccountError, USERS


def main():
    parser=argparse.ArgumentParser(description='为五人试用设置临时密码；首次登录必须改密。')
    parser.add_argument('--reset',choices=USERS,help='显式重置一个账号，保留聊天与偏好')
    parser.add_argument('--check',action='store_true',help='只检查五个账号是否已初始化，不打印凭证')
    parser.add_argument('--shared-temporary',action='store_true',help='隐藏输入一次共享临时密码（至少6位），仅初始化尚不存在的账号')
    args=parser.parse_args()
    store=AccountStore()
    from backend.storage import read
    existing=read(store.path, {'users':{}})['users']
    if args.check:
        missing=[n for n in USERS if n not in existing]
        if missing:
            print('Accounts not initialized: '+', '.join(missing));return 1
        print('All five accounts initialized.');return 0
    if not sys.stdin.isatty():
        print('Use a local interactive terminal; passwords must not be piped or logged.');return 1
    if args.shared_temporary:
        if args.reset:parser.error('--shared-temporary cannot be combined with --reset')
        missing=[n for n in USERS if n not in existing]
        if not missing:
            print('All accounts already exist; no passwords changed.');return 0
        password=getpass.getpass('Shared temporary password (6-128 characters): ')
        again=getpass.getpass('Repeat: ')
        if password!=again:raise AccountError('Passwords differ; no accounts changed.')
        for name in missing:
            store.provision(name,password,temporary=True)
        password=again=None
        print('Initialized: '+', '.join(missing)+'. First login requires a personal password.')
        return 0
    for name in ([args.reset] if args.reset else [n for n in USERS if n not in existing]):
        while True:
            try:
                password=getpass.getpass(f'{name} temporary password (12-128 characters): ')
                again=getpass.getpass('Repeat: ')
                if password!=again:
                    print('Passwords differ.');continue
                store.provision(name,password,reset=bool(args.reset))
                password=again=None
                print(f'{name}: ready; first login requires a new password.')
                break
            except AccountError as e:print(str(e))
    return 0


if __name__=='__main__':
    try:raise SystemExit(main())
    except (EOFError,KeyboardInterrupt):raise SystemExit('Setup cancelled; existing accounts preserved.')
