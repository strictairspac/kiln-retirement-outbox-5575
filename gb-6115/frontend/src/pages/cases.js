import { api } from "../api/workbench.js";
import { errorText, field } from "../components/common/fields.js";
import { empty, pageHeading, section } from "../components/common/panel.js";
import { table } from "../components/common/table.js";
import { submit } from "../hooks/submit.js";
import { navigate } from "../router/router.js";
import { el } from "../utils/dom.js";
import { time } from "../utils/format.js";

const ORIGINS = ["设备组", "档案室"];
const KIND = {asset: "炉号", certificate: "证书号"};

const BatchStates = Object.freeze({
  held: "已占号", rejected: "整批退回", succeeded: "已交卷", failed: "执行失败",
});

function batchStatus(value) {
  return el("span", {class: `status state-batch-${value}`, "data-batch-state": value}, BatchStates[value] || value);
}

function list(value) {
  return Array.isArray(value) ? value : [];
}

function numbers(value) {
  const entries = list(value);
  return entries.length ? entries.map(item => `${KIND[item.number_kind] || item.number_kind} ${item.number_code}`).join("；") : "—";
}

function collisions(value) {
  const entries = list(value);
  return entries.length ? entries.map(item =>
    `${KIND[item.number_kind] || item.number_kind} ${item.number_code} → ${item.holder_code}（${item.holder_title}）`).join("；") : "—";
}

function ledgerSection(batches) {
  return section("正式批次判定", ledgerBody(batches));
}

function caseBatch(selected, batches) {
  if (!selected) return null;
  return batches.find(batch => batch.case_id === selected.id) || null;
}

function queueForm(config, selected, batch) {
  const formal = Boolean(selected.payload?.origin);
  if (formal && batch && batch.status !== "held") {
    return el("div", {class: "stack"}, batchStatus(batch.status), el("p", {}, batch.verdict),
      el("p", {class: "empty"}, "该正式批次已结束。编号释放后请重新登记，不要在此重复提交。"));
  }
  if (formal && batch?.run_id) {
    return el("div", {class: "stack"}, batchStatus(batch.status), el("p", {}, batch.verdict),
      el("a", {href: `#runs/${batch.run_id}`}, "查看执行进度"));
  }
  const form = el("form", {class: "queue-form"},
    field(config.parameter_label, el("input", {
      name: "parameter", type: "number", min: 1, max: config.max_parameter, required: true, value: config.default_parameter,
    })),
    el("button", {type: "submit"}, formal ? "提交正式批次" : "提交回放"), errorText());
  submit(form, async values => {
    const run = await api.enqueue(selected.id, {parameter: Number(values.get("parameter"))});
    navigate(`runs/${run.id}`);
  });
  return el("div", {class: "stack"}, formal && batch ? [batchStatus(batch.status), el("p", {}, batch.verdict), form] : form);
}

function registration(config, selected, onVerdict) {
  const template = selected ? {...selected.payload} : {
    origin: "设备组",
    requests: [{asset: "OV-301", certificate: "RET-1201-01", failed_stage: "none"}],
  };
  if (selected) delete template.origin;
  const form = el("form", {id: "case-form"},
    field("名称", el("input", {name: "title", required: true, minlength: 2, maxlength: 120, value: selected ? `${selected.title} · 复演` : ""})),
    field("说明", el("input", {name: "description", maxlength: 420, value: selected?.description || ""})),
    field(`${config.unit}内容`, el("textarea", {name: "payload", spellcheck: "false", required: true, rows: 12}, JSON.stringify(template, null, 2)),
      "含 origin（设备组或档案室）为正式批次；不含 origin 为演练回放，不占用正式编号。"),
    errorText(), el("button", {type: "submit"}, "保存资料"));
  submit(form, async values => {
    let payload;
    try {
      payload = JSON.parse(values.get("payload"));
    } catch {
      throw new Error("资料 JSON 无法解析，请检查括号、引号和逗号");
    }
    if (payload?.origin && !ORIGINS.includes(payload.origin)) {
      throw new Error("正式批次来源只支持设备组、档案室；演练请删除 origin");
    }
    const result = await api.createCase({title: values.get("title"), description: values.get("description"), payload});
    if (result.accepted && result.case) {
      navigate(`cases/${result.case.id}`);
      return;
    }
    onVerdict?.(result);
    throw new Error(result.verdict);
  });
  return form;
}

function ledgerBody(batches) {
  return batches.length ?
    table(["批次", "来源", "判定", "判定说明", "本批编号", "撞号占用", "进档", "登记时间"], batches.map(batch => [
      batch.code, batch.origin, batchStatus(batch.status), batch.verdict, numbers(batch.numbers),
      collisions(batch.collisions), `${batch.archived} 张`, time(batch.created_at)]), "正式批次判定") :
    empty("还没有正式退役批次。登记时写明来源「设备组」或「档案室」即为正式批次。");
}

export async function casesPage(config, user, route) {
  const [cases, batches] = await Promise.all([api.cases(), api.batches()]);
  const selected = cases.find(item => item.id === route.id) ?? cases.at(-1);
  const operator = user.role === "operator";
  const ledger = ledgerSection(batches);
  const reload = async () => {
    // 登记被整批退回后，就地刷新判定台账，不打断已填的表单。
    try {
      ledger.lastElementChild?.replaceWith(ledgerBody(await api.batches()));
    } catch {
      // 刷新失败保留原台账，错误信息仍由表单展示。
    }
  };
  return el("div", {class: "page"},
    pageHeading(config.modules[1], `${config.unit} · ${config.fixture}`),
    ledger,
    section("资料目录", cases.length ? table(["编号", "名称", "说明", "操作"], cases.map(item =>
      [item.code, item.title, item.description,
        el("a", {href: `#cases/${item.id}`, "aria-current": item.id === selected?.id ? "true" : null}, "选用")]), "资料目录") :
      empty("这里还没有资料。")),
    el("div", {class: "split case-split"},
      section(selected ? selected.title : "等待选择资料", selected ?
        [el("p", {}, selected.description),
          operator ? queueForm(config, selected, caseBatch(selected, batches)) : empty("当前账号可查看此资料。"),
          el("details", {}, el("summary", {}, "查看业务数据"), el("pre", {}, JSON.stringify(selected.payload, null, 2)))] :
        empty("先登记一条资料，再提交执行。")),
      operator ? section("登记新资料", registration(config, selected, reload)) : null));
}
