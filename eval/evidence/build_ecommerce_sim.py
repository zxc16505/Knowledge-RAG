# -*- coding: utf-8 -*-
"""
构造「模拟中型电商企业知识库」评测集（脱敏 · 仿真电商场景）
====================================================
模拟一个真实体量的电商企业知识库：四大品牌（百斯盾 / 猫人 / 红豆 / 百家好）、
覆盖商品成分规格、尺码对照、颜色与编码映射、销售报表、库存、各部门 SOP、
平台规则、合格证 BI 规范。规模远大于原 9~14 篇黄金集，用于验证
「向量单阶段」vs「向量+Rerank 双阶段」在更接近真实电商语料下的表现。
文档均为仿真构造，不含任何真实业务机密；编码规则沿用公开已知的品牌编码常识。
输出：golden_set_ecom.json
"""
import json
import os

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "golden_set_ecom.json")

docs = {}
def add(doc_id, text):
    docs[doc_id] = text

# ---------- 1. 商品成分与规格（多品牌、相似品类制造检索难度）----------
add("ecom_cat_maoren_a",
    "猫人保暖内衣经典系列A款：面料成分为腈纶70%、氨纶30%；里料为纯棉。"
    "克重320g/m²，适合0-15℃穿着。尺码范围S-3XL，领口圆领，颜色黑/灰/藏青。"
    "执行标准FZ/T 73022，安全类别B类（可直接接触皮肤）。")
add("ecom_cat_maoren_b",
    "猫人保暖内衣发热系列B款：面料成分为腈纶65%、氨纶35%，添加吸湿发热纤维；"
    "里料纯棉。克重280g/m²，适合5-18℃穿着。尺码S-3XL，半高领设计。"
    "执行标准FZ/T 73022，安全类别B类。注意B款与A款成分接近但克重不同。")
add("ecom_cat_maoren_c",
    "猫人男士秋衣秋裤纯棉套装C款：面料100%棉，里料100%棉，无氨纶。"
    "克重260g/m²，适合10-20℃家居穿着。圆领长袖，尺码M-2XL。"
    "执行标准FZ/T 73024，安全类别A类（婴幼儿可用级别）。")
add("ecom_cat_baishidun_pants",
    "百斯盾男士运动裤：面料锦纶88%、氨纶12%，四面弹力速干；里料网眼布。"
    "膝部拼接加固，适合跑步健身。尺码28-38码（腰围）。颜色黑/深灰/藏青。"
    "执行标准GB/T 22853，安全类别B类。")
add("ecom_cat_baishidun_jacket",
    "百斯盾防风夹克：面料100%聚酯纤维，内里抓绒；袖口弹力收口。"
    "防风防泼水，适合春秋户外。尺码M-3XL。执行标准FZ/T 81007，B类。")
add("ecom_cat_hongdou_tee",
    "红豆男士纯棉短袖T恤：面料100%棉（新疆长绒棉），克重210g/m²，支数40S。"
    "圆领基础款，尺码S-3XL，颜色白/黑/藏青/麻灰。执行标准FZ/T 73043，A类。"
    "注意红豆T恤为纯棉，与猫人发热B款（含腈纶氨纶）成分明显不同。")
add("ecom_cat_hongdou_shirt",
    "红豆长袖衬衫：面料棉60%、聚酯纤维40%，免烫抗皱处理。尺码38-44（领围）。"
    "商务通勤款，颜色白/浅蓝/深灰。执行标准FZ/T 13043，B类。")
add("ecom_cat_baijiahao_coat",
    "百家好女士羊毛大衣：面料羊毛70%、聚酯纤维30%；里料聚酯纤维。"
    "中长款双面呢，尺码S-XL。颜色驼色/黑色/藕粉。执行标准FZ/T 81010，B类。")
add("ecom_cat_baijiahao_dress",
    "百家好连衣裙：面料聚酯纤维95%、氨纶5%，微弹垂感。尺码S-XL。"
    "收腰显瘦款，颜色杏色/黑色/雾蓝。执行标准FZ/T 81004，B类。")

# ---------- 2. 尺码对照（相似结构，考验跨品牌区分）----------
add("ecom_size_maoren",
    "猫人尺码对照表：S(身高160-165cm,体重45-50kg)、M(165-170,50-58)、"
    "L(170-175,58-65)、XL(175-180,65-72)、2XL(180-185,72-80)、3XL(185-190,80-88)。")
add("ecom_size_baishidun",
    "百斯盾尺码对照表（以裤装腰围为准）：28码(腰围71cm)、29(74)、30(76)、"
    "31(79)、32(82)、33(85)、34(88)、36(93)、38(98)。")
add("ecom_size_hongdou",
    "红豆尺码对照表：S(160-165,45-50)、M(165-170,50-58)、L(170-175,58-65)、"
    "XL(175-180,65-72)、2XL(180-185,72-80)、3XL(185-190,80-90)。")
add("ecom_size_baijiahao",
    "百家好女装尺码对照表：S(155-160,40-45)、M(160-165,45-52)、"
    "L(165-170,52-58)、XL(170-175,58-65)。女装尺码偏小，建议拍大一码。")

# ---------- 3. 颜色编码映射 ----------
add("ecom_color_hongdou",
    "红豆颜色编码映射表（店铺维度，标准列=上一颜色编号+1）："
    "01黑、02白、03藏青、04麻灰、05酒红、06卡其、07军绿、08杏色。"
    "新颜色自动追加递增编号，无需预置映射表。")
add("ecom_color_baijiahao",
    "百家好颜色编码映射（供应商款号内嵌）：驼色-TU、黑色-BK、藕粉-OF、"
    "杏色-AP、雾蓝-WB、香槟-CH。百家好不依赖颜色/尺码编号映射表，"
    "新颜色无需追加映射条目，编码格式 BJH-供应商款号-颜色-尺码。")

# ---------- 4. 商品编码规则 ----------
add("ecom_code_hongdou",
    "红豆商品编码规则：编码=品牌前缀+供应商款式编码+颜色编号+尺码编号。"
    "例：红豆男T恤 供应商XT 款号6629 黑色S → 编码 HD-M-XT-6629-01-S。"
    "品牌专属规则，仅作用于红豆，不影响其他品牌（猫人/百斯盾/百家好）编码格式。")
add("ecom_code_baijiahao",
    "百家好分销编码规则：编码=BJH-供应商款号-颜色-尺码。"
    "供应商款号=供应商名称+供应商货号；供应商款式编码列需加 M- 前缀。"
    "例：M-XT-UKNZ-6629 驼色 S → BJH-M-XT-UKNZ-6629-TU-S。"
    "百家好已废弃颜色数/尺码数映射表，新颜色无需追加映射条目。")

# ---------- 5. 销售与库存报表 ----------
add("ecom_sales_202608",
    "2026年8月销售汇总：全店GMV 386万元，环比+12%。"
    "品牌占比：猫人38%、红豆27%、百斯盾21%、百家好14%。"
    "top品类：保暖内衣(猫人)、纯棉T恤(红豆)、运动裤(百斯盾)。"
    "客单价182元，退货率4.1%。")
add("ecom_sales_202609",
    "2026年9月销售周报（截至第3周）：GMV 271万元，同比+9%。"
    "秋装上新带动衬衫(红豆)、夹克(百斯盾)增长明显。"
    "直播渠道占比升至35%，抖音小店日销破万单。")
add("ecom_stock_weekly",
    "库存周转周报：整体周转天数42天，目标≤45天。保暖内衣库存预警（低于安全库存15%）。"
    "运动裤滞销SKU 3个建议清仓。重点看指标：周转天数、动销率、售罄率、库龄结构。")

# ---------- 6. 各部门 SOP ----------
add("ecom_sop_storage",
    "仓储入库SOP：到货扫码→核对采购单→质检抽样(抽检率5%)→上架库位→"
    "系统录入库存。异常（破损/少件）2小时内上报采购。冷链/易碎品单独分区。")
add("ecom_sop_pick",
    "拣货打包SOP：订单波次下发→纸质/RF拣货→复核扫码→填充缓冲材料→"
    "称重出库。错发率要求<0.2%，打包合格率≥99%。")
add("ecom_sop_logistics",
    "物流发货SOP：京东自营仓发当日达/次日达；天猫店普通快递48小时揽收；"
    "抖音小店电子面单自动回传。大促（双11）启用预售分批发货，"
    "现货订单承诺72小时内发出。异常物流主动跟进并安抚客户。")
add("ecom_sop_aftersale",
    "售后处理SOP：7天无理由退换（吊牌完整）；质量问题48小时内审核并承担运费；"
    "尺寸不合可换码。退换货审核节点：客户申请→客服初审→仓库验货→退款/重发。"
    "纠纷升级至主管，24小时内响应。")
add("ecom_sop_service",
    "客服应答SOP：首响≤30秒，标准话术库覆盖成分/尺码/物流/退换。"
    "成分类问题引用商品详情页标准文案；尺码类引导对照表；"
    "情绪客户先共情再解决。满意度目标≥95%。")
add("ecom_sop_finance",
    "财务对账SOP：每日平台流水与ERP对账，差异>100元当日核查；"
    "月结供应商货款T+15；退款订单单独挂账。开票信息与订单一致。")
add("ecom_sop_listing",
    "运营上架SOP：选品→填商品信息(标题/类目/属性)→提交审核→"
    "上架后巡检价格库存。自动化上架由RPA从商品数据包按品类模板批量生成，"
    "34天产出410条上架记录、385唯一ID，峰值单日52款。")
add("ecom_sop_data",
    "数据治理SOP：商品主数据统一编码；SKU字段标准化（68字段模板）；"
    "跨平台数据每日同步；脏数据(重复/缺图)拦截率目标100%。"
    "主数据变更需审批留痕。")

# ---------- 7. 平台规则 ----------
add("ecom_rule_jd",
    "京东自营退换货规则：自营商品支持7天无理由退货（不影响二次销售），"
    "质量问题15天内可换。退款原路返回，时效1-3个工作日。自营仓发优先。")
add("ecom_rule_tmall",
    "天猫店铺评分规则：DSR包含描述相符、服务态度、物流服务三项，"
    "每项5分制，店铺需维持≥4.7。低于4.5触发预警；退货率影响搜索权重。")
add("ecom_rule_douyin",
    "抖音直播带货规范：主播需实名认证；禁止虚假宣传与绝对化用语；"
    "商品须挂载小黄车；限时秒杀需标注真实原价。违禁词实时拦截。")

# ---------- 8. 合格证与 BI ----------
add("ecom_cert",
    "合格证与BI模板规范：合格证须含款式、颜色、规格、执行标准、安全类别、吊牌价。"
    "从合格证提取上述字段转换至BI模板，按色按码生成。吊牌价单位元，保留整数。")

# ---------- 查询集（真实业务提问，relevant 指向对应文档）----------
queries = [
    {"query": "猫人保暖内衣经典A款的面料成分是什么", "relevant": ["ecom_cat_maoren_a"]},
    {"query": "猫人发热B款含不含氨纶，比例多少", "relevant": ["ecom_cat_maoren_b"]},
    {"query": "猫人纯棉套装C款是不是A类安全类别", "relevant": ["ecom_cat_maoren_c"]},
    {"query": "百斯盾运动裤面料成分和弹性怎么样", "relevant": ["ecom_cat_baishidun_pants"]},
    {"query": "百斯盾防风夹克防风吗，什么面料", "relevant": ["ecom_cat_baishidun_jacket"]},
    {"query": "红豆纯棉T恤是纯棉的吗还是含化纤", "relevant": ["ecom_cat_hongdou_tee"]},
    {"query": "红豆长袖衬衫免烫吗，成分比例", "relevant": ["ecom_cat_hongdou_shirt"]},
    {"query": "百家好羊毛大衣含羊毛多少", "relevant": ["ecom_cat_baijiahao_coat"]},
    {"query": "百家好连衣裙有弹性吗", "relevant": ["ecom_cat_baijiahao_dress"]},
    {"query": "猫人S码对应什么身高体重", "relevant": ["ecom_size_maoren"]},
    {"query": "百斯盾32码腰围多少", "relevant": ["ecom_size_baishidun"]},
    {"query": "红豆XL尺码范围", "relevant": ["ecom_size_hongdou"]},
    {"query": "百家好女装偏大还是偏小", "relevant": ["ecom_size_baijiahao"]},
    {"query": "红豆颜色编码里黑色和藏青分别是什么号", "relevant": ["ecom_color_hongdou"]},
    {"query": "百家好驼色颜色编码是什么", "relevant": ["ecom_color_baijiahao"]},
    {"query": "红豆商品编码规则怎么组成", "relevant": ["ecom_code_hongdou"]},
    {"query": "百家好分销编码格式是什么，供应商款号怎么写", "relevant": ["ecom_code_baijiahao"]},
    {"query": "2026年8月全店销售额和品牌占比", "relevant": ["ecom_sales_202608"]},
    {"query": "9月销售周报直播渠道占比多少", "relevant": ["ecom_sales_202609"]},
    {"query": "库存周转看哪些指标", "relevant": ["ecom_stock_weekly"]},
    {"query": "仓储入库流程是什么", "relevant": ["ecom_sop_storage"]},
    {"query": "拣货打包合格率和错发率要求", "relevant": ["ecom_sop_pick"]},
    {"query": "双11大促物流发货时效承诺", "relevant": ["ecom_sop_logistics"]},
    {"query": "质量问题退货运费谁承担", "relevant": ["ecom_sop_aftersale"]},
    {"query": "客服首响时间要求多少", "relevant": ["ecom_sop_service"]},
    {"query": "财务对账差异超过多少要核查", "relevant": ["ecom_sop_finance"]},
    {"query": "自动化上架34天出了多少条记录", "relevant": ["ecom_sop_listing"]},
    {"query": "商品主数据字段标准化有多少字段", "relevant": ["ecom_sop_data"]},
    {"query": "京东自营七天无理由退货规则", "relevant": ["ecom_rule_jd"]},
    {"query": "天猫店铺DSR评分要维持多少", "relevant": ["ecom_rule_tmall"]},
    {"query": "抖音直播不能说绝对化用语吗", "relevant": ["ecom_rule_douyin"]},
    {"query": "合格证必须包含哪些字段", "relevant": ["ecom_cert"]},
    {"query": "猫人保暖内衣和红豆T恤哪个更厚", "relevant": ["ecom_cat_maoren_a", "ecom_cat_hongdou_tee"]},
    {"query": "百家好和红豆的尺码表能通用吗", "relevant": ["ecom_size_hongdou", "ecom_size_baijiahao"]},
]

data = {
    "meta": {
        "desc": "模拟中型电商企业知识库评测集（脱敏仿真，四大品牌）",
        "n_documents": len(docs),
        "n_queries": len(queries),
        "note": "文档为仿真构造，非真实业务数据；用于验证检索架构在电商语料规模下的表现"
    },
    "documents": [{"id": k, "text": v} for k, v in docs.items()],
    "queries": queries,
}

os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
print(f"[*] 已生成 {OUT}")
print(f"[*] 文档数={len(docs)} 查询数={len(queries)}")
# 简单自检：relevant 是否都存在于 docs
missing = [q["query"] for q in queries if any(r not in docs for r in q["relevant"])]
print("[*] 缺失 relevant 的查询:", missing if missing else "无")
