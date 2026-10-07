"""Names from the supplied 2026-09-17 inventory and BNU dining guide.
Menus below are synthetic fixtures, never an observation of a merchant's menu.
"""
GUIDE = "https://zwb.bnu.edu.cn/fwzn/jdfw/index.htm"
INVENTORY = "北师大海淀校园餐饮与外卖数据清单.md / 2026-09-17"
# id, name, address, category, opening intervals, building, floor, source, access
VENUES = [
 ("canteen-1","学一食堂","新乐群一层","canteen",[["06:30","09:00"],["10:30","13:30"],["16:30","20:00"]],499434918,"1",GUIDE,"students"),
 ("canteen-2","学二食堂","新乐群二层","canteen",[["10:30","13:15"],["16:30","19:15"]],499434918,"2",GUIDE,"students"),
 ("canteen-3","学三食堂","新乐群三层","canteen",[["10:30","13:30"],["16:30","20:00"]],499434918,"3",GUIDE,"students"),
 ("canteen-4","学四食堂","新乐群四层","canteen",[["10:00","14:00"],["16:00","21:00"]],499434918,"4",GUIDE,"students"),
 ("canteen-5","学五食堂","学五食堂一层、二层及阁楼","canteen",None,None,"",GUIDE,"students"),
 ("canteen-6","学六食堂","留学生食堂一、二层","canteen",[["11:00","13:30"],["17:00","20:00"]],None,"",GUIDE,"students"),
 ("yixin","一心日料","学六食堂区域","restaurant",[["11:00","14:00"],["16:00","21:00"]],None,"",GUIDE,"students"),
 ("canteen-7","学七食堂","南院A座负一层","canteen",[["06:30","09:30"],["10:30","13:00"],["16:30","19:00"]],None,"-1",GUIDE,"students"),
 ("halal","清真食堂","海淀校园，具体位置待核","canteen",[["06:30","08:30"],["10:30","12:50"],["16:30","18:30"]],None,"",GUIDE,"students"),
 ("staff-1","教工一食堂","海淀校园，具体位置待核","canteen",[["06:30","09:00"],["10:30","13:00"],["16:30","19:00"]],None,"",GUIDE,"staff"),
 ("staff-2","教工二食堂","实习餐厅","canteen",None,None,"",GUIDE,"staff"),
 ("lanhui","兰蕙餐厅","兰蕙公寓，一层教工餐、二层零点","restaurant",[["06:30","09:00"],["11:00","13:00"],["16:30","20:00"]],900000000001,"2",GUIDE,"unknown"),
 ("mcd","麦当劳北师大店","励耘学苑一层","restaurant",None,None,"1",INVENTORY,"students"),
 ("luckin","瑞幸咖啡北京师范大学科技楼店","科技楼二层大厅","coffee",None,None,"2",INVENTORY,"students"),
 ("starbucks","星巴克","美食街南侧二层","coffee",None,None,"2",INVENTORY,"students"),
 ("jiupin","九榀咖啡","家属区中昌华美超市旁","coffee",None,None,"",INVENTORY,"students"),
 ("granada","加纳达咖啡","学十九楼二层","coffee",None,None,"2",INVENTORY,"students"),
 ("wugu","五谷坊","学五食堂西侧","restaurant",None,None,"",INVENTORY,"students"),
 ("laixifu","来喜福","学五食堂北侧","restaurant",None,None,"",INVENTORY,"students"),
 ("xiaomi","小米鸡排","学五食堂北侧","restaurant",None,None,"",INVENTORY,"students"),
 ("bayi","巴依老爷新疆美食（北师大店）","学院南路16号，南门斜对面","restaurant",None,None,"",INVENTORY,"public"),
 ("xiang","嬲塞de湘菜馆（北师大店）","北三环中路44号底商一层","restaurant",None,None,"1",INVENTORY,"public"),
 ("ziguang","紫光园清真北京小吃（今典花园店）","文慧园北路9号","restaurant",None,None,"",INVENTORY,"public"),
 ("jitian","集天小吃（北师大店）","东门留学生公寓区域，校内外待核","restaurant",None,None,"",INVENTORY,"unknown"),
]
DISHES = [
 ("辣味鸡肉饭",18,["辣","鸡肉","米饭"]),("番茄鸡蛋面",12,["清淡","面","鸡蛋"]),
 ("牛肉粉",16,["牛肉","粉"]),("水饺",15,["饺子","猪肉"]),
 ("蔬菜拌面",13,["蔬菜","面"]),("香辣豆腐饭",14,["辣","米饭","豆制品"]),
 ("鸡肉卷",17,["鸡肉","饼"]),("酸辣土豆粉",14,["辣","粉"]),
 ("番茄牛肉饭",22,["牛肉","米饭"]),("杂粮蔬菜套餐",15,["蔬菜","杂粮"]),
]

