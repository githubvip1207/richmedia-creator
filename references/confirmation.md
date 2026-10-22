# Task confirmation and user selection

## Data sources

Use the requirements in request.json, the current optimized prompt and parameters, and the saved estimate in each supplier's cost.json. Do not recalculate prices.

Resolve supplier names from PROVIDERS in scripts/providers/__init__.py. Offer generation only for suppliers meeting the task prerequisites. If the user specified a supplier, show only that supplier; if none is available, explain why.

## Display format

Place the complete sheet directly in the **final response body**, not inside a code block or replaced by an attachment or tool output.

```markdown
# 任务确认单

提示词：{Complete optimized prompt; explain prompt-free automatic decomposition when applicable}

参数概要：

- 模型：{Current model} [{Available models}]
- 比例：{Current ratio} [{Available ratios}]
- 分辨率：{Image tier/exact pixels or video resolution} [{Available values}]
- 数量：{Current count} [{Available values}]
{Add video duration and other applicable settings in the same list format}

费用预估：

- {Supplier name}：{Native-currency amount/range/unknown; add CNY conversion when valid}
{One item per supplier}

生成提示：

- {Applicable FX and expiration, cost uncertainty or decision-relevant limits}
- 实际费用以供应商结算为准。

请选择供应商确认生成，或选择“我再想想”。
```

- List only values supported by the current model and operation. Note any differences between supplier offers.
- Use amounts, FX and expiration from the saved cost results. Keep native currency without valid FX and explicitly label unknown upper costs.
- Hide tokens, price-snapshot sources, API endpoints, credentials and other internal fields.

## User selection

Use request_user_input_async for selectable options and optional free-text input. The call returns immediately; the actual answer arrives in a subsequent user message.

1. Generate one `{供应商名称}，确认生成` option per eligible supplier. For unknown upper costs use `{供应商名称}，接受费用上界未知并确认生成`. Append only `我再想想`.
2. After calling the tool, end the turn with the complete sheet in the final response. Execute the chosen supplier only after receiving an actual generation selection, without asking for a second confirmation. See the [CLI manual](usage.md) for submission.
3. `我再想想` leaves generation unsubmitted while awaiting further instructions. Silence, preselection or dismissal is not confirmation. Free-text changes require an updated sheet and confirmation.

Example (generate supplier options from this task):

```javascript
request_user_input_async({
  questions: [{
    title: "请选择本次任务确认单的方案",
    options: [...supplierConfirmationOptions, "我再想想"]
  }]
})
```

If the tool is unavailable, display the complete final sheet and wait for an explicit user reply. Do not present Markdown lists as clickable controls.
