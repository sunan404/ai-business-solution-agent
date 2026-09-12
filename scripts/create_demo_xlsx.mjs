import fs from "node:fs/promises";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const outputDir = "data";
await fs.mkdir(outputDir, { recursive: true });
const workbook = Workbook.create();

const interview = workbook.worksheets.add("客户访谈（虚构）");
interview.showGridLines = false;
interview.getRange("A1:F1").merge();
interview.getRange("A1").values = [["澄野生活：渠道与活动协作访谈（虚构案例）"]];
interview.getRange("A2:F2").merge();
interview.getRange("A2").values = [["所有公司、人员、业务数据及描述均为虚构，仅用于作品集演示。"]];
interview.getRange("A4:F4").values = [["主题", "原始访谈摘录", "涉及角色", "现有工具", "频率/时限", "客户关注点"]];
interview.getRange("A5:F10").values = [
  ["业务目标", "管理团队希望在未来两个季度提升华东区域经销商覆盖，并把活动复盘准备时间从三天缩短到一天。", "管理团队、市场、销售", "季度经营会", "两个季度", "希望用同一套资料和指标支持区域决策"],
  ["经销商资料", "经销商合同、价格表和联系人分散在销售个人文件夹、共享盘和聊天记录。销售主管每周交接时常找不到最新版本。", "销售、渠道运营", "个人文件夹、共享盘、即时消息", "每周", "担心客户问题响应慢、合作机会遗漏"],
  ["市场活动", "活动排期、物料版本和审批使用三个 Excel 文件。市场、设计和门店团队无法在同一处确认负责人及截止时间，本月有两场门店活动延期。", "市场、设计、门店", "Excel、即时消息", "本月", "希望在活动开始前发现延期风险"],
  ["活动复盘", "门店、社媒和经销商活动数据需要运营同事手工汇总；到店、线索和成交的指标口径不同，月度复盘准备平均需要三天。", "市场、运营、销售", "CSV、Excel", "每月", "希望统一口径后比较活动带来的线索和成交"],
  ["费用与物料", "促销预算和对外物料审批依赖聊天确认，审批人、最终版本和确认时间没有统一流程记录。", "市场、财务、管理者", "即时消息", "按需", "负责人担心旺季前出现漏批或版本错误"],
  ["推进边界", "管理团队要求先选一个问题试点，明确资料负责人、审批责任人和衡量成效的指标，再决定是否扩大到全部区域。", "管理团队", "季度经营会", "下次经营会", "关注试点周期、投入与可量化改善"],
];

const data = workbook.worksheets.add("活动数据（虚构）");
data.showGridLines = false;
data.getRange("A1:G1").merge();
data.getRange("A1").values = [["春季区域活动摘录（虚构数据，仅供诊断示例）"]];
data.getRange("A3:G3").values = [["活动", "区域", "数据来源", "到店口径", "线索口径", "成交口径", "复盘备注"]];
data.getRange("A4:G7").values = [
  ["新品体验日", "上海", "门店导出", "签到人数", "扫码留资", "门店手工登记", "门店和销售表的线索数相差 18 条"],
  ["新品体验日", "杭州", "社媒后台", "直播观看", "私信咨询", "CRM 导出", "无法按同一活动编号关联"],
  ["经销商沙龙", "南京", "Excel 汇总", "到场经销商", "意向订货", "销售口头反馈", "成交字段在周报中缺失"],
  ["经销商沙龙", "苏州", "渠道运营 CSV", "报名人数", "现场登记", "CRM 导出", "数据在复盘前一天才完成汇总"],
];

for (const sheet of [interview, data]) {
  sheet.getRange("A1:G1").format = { fill: "#1F4E78", font: { name: "Arial", size: 14, bold: true, color: "#FFFFFF" }, horizontalAlignment: "left", verticalAlignment: "center" };
  sheet.getRange("A1:G1").format.rowHeight = 28;
  sheet.getRange("A:A").format.columnWidth = 16;
  sheet.getRange("B:B").format.columnWidth = 45;
  sheet.getRange("C:C").format.columnWidth = 20;
  sheet.getRange("D:D").format.columnWidth = 24;
  sheet.getRange("E:E").format.columnWidth = 16;
  sheet.getRange("F:F").format.columnWidth = 30;
  sheet.getRange("G:G").format.columnWidth = 31;
}
interview.getRange("A2:F2").format = { font: { name: "Arial", size: 10, italic: true, color: "#5B6876" } };
interview.getRange("A4:F4").format = { fill: "#DCEAF7", font: { name: "Arial", size: 10, bold: true, color: "#203040" }, horizontalAlignment: "center", verticalAlignment: "center" };
interview.getRange("A5:F10").format = { font: { name: "Arial", size: 10, color: "#263746" }, wrapText: true, verticalAlignment: "top", borders: { preset: "inside", style: "thin", color: "#D9E1E8" } };
interview.getRange("A4:F10").format.borders = { preset: "outside", style: "thin", color: "#AABBCB" };
interview.getRange("A5:F10").format.rowHeight = 68;
interview.freezePanes.freezeRows(4);
data.getRange("A3:G3").format = { fill: "#DCEAF7", font: { name: "Arial", size: 10, bold: true, color: "#203040" }, horizontalAlignment: "center", verticalAlignment: "center" };
data.getRange("A4:G7").format = { font: { name: "Arial", size: 10, color: "#263746" }, wrapText: true, verticalAlignment: "top", borders: { preset: "inside", style: "thin", color: "#D9E1E8" } };
data.getRange("A3:G7").format.borders = { preset: "outside", style: "thin", color: "#AABBCB" };
data.getRange("A4:G7").format.rowHeight = 50;
data.freezePanes.freezeRows(3);

workbook.recalculate();
console.log((await workbook.inspect({ kind: "table", range: "客户访谈（虚构）!A1:F10", include: "values,formulas", tableMaxRows: 10, tableMaxCols: 6 })).ndjson);
console.log((await workbook.inspect({ kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!", options: { useRegex: true, maxResults: 50 }, summary: "formula error scan" })).ndjson);
const preview = await workbook.render({ sheetName: "客户访谈（虚构）", range: "A1:F10", scale: 1.2, format: "png" });
await fs.writeFile("data/demo_consumer_brand_preview.png", new Uint8Array(await preview.arrayBuffer()));
const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(`${outputDir}/demo_consumer_brand.xlsx`);

