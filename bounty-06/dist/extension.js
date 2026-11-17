// RAEN IDE Extension for VS Code and Cursor
const DEFAULT_GATEWAY_URL = "https://raen-mcp-gateway.fly.dev/mcp";
const DEFAULT_CATALOG_URL = "https://raw.githubusercontent.com/bshelby88/raen-agent-directory/main/llms.txt";

class RaenMcpClient {
  constructor(gatewayUrl = DEFAULT_GATEWAY_URL, apiKey, timeoutMs = 25000) {
    this.gatewayUrl = (gatewayUrl || DEFAULT_GATEWAY_URL).replace(/\/+$/, "");
    this.apiKey = apiKey || process.env.RAEN_API_KEY || process.env.RAEN_MCP_KEY;
    this.timeoutMs = timeoutMs;
    this.reqId = 1;
  }

  setApiKey(key) {
    this.apiKey = key;
  }

  getApiKey() {
    return this.apiKey;
  }

  getGatewayUrl() {
    return this.gatewayUrl;
  }

  async postJsonRpc(method, params = {}) {
    const id = this.reqId++;
    const headers = {
      "Content-Type": "application/json",
      "User-Agent": "raen-ide-extension/1.0.0",
      "Accept": "application/json",
    };

    if (this.apiKey) {
      headers["Authorization"] = `Bearer ${this.apiKey.trim()}`;
    }

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), this.timeoutMs);

    try {
      const resp = await fetch(this.gatewayUrl, {
        method: "POST",
        headers,
        body: JSON.stringify({
          jsonrpc: "2.0",
          id,
          method,
          params,
        }),
        signal: controller.signal,
      });

      clearTimeout(timeout);

      if (resp.status === 402) {
        const errorJson = await resp.json().catch(() => ({}));
        const err = new Error(`x402 Payment Required: ${errorJson?.error || "Payment challenge"}`);
        err.status = 402;
        err.challenge = errorJson;
        throw err;
      }

      if (resp.status === 401 || resp.status === 403) {
        throw new Error(`Auth failed (${resp.status}): Invalid or missing Bearer key.`);
      }

      if (!resp.ok) {
        const txt = await resp.text().catch(() => "");
        throw new Error(`Gateway returned HTTP ${resp.status}: ${txt}`);
      }

      const json = await resp.json();
      if (json.error) {
        throw new Error(`MCP Error [${json.error.code}]: ${json.error.message}`);
      }

      return {
        result: json.result,
        headers: resp.headers,
        raw: json,
      };
    } catch (err) {
      clearTimeout(timeout);
      if (err.name === "AbortError") {
        throw new Error(`Request timed out after ${this.timeoutMs}ms`);
      }
      throw err;
    }
  }

  async initialize() {
    const res = await this.postJsonRpc("initialize", {
      protocolVersion: "2025-03-26",
      capabilities: {},
      clientInfo: { name: "raen-ide-extension", version: "1.0.0" },
    });
    return res.result;
  }

  async listTools() {
    const res = await this.postJsonRpc("tools/list", {});
    return res.result?.tools || [];
  }

  async callTool(name, args) {
    try {
      const res = await this.postJsonRpc("tools/call", {
        name,
        arguments: args,
      });

      const paymentReceipt = res.headers?.get("x-payment-response") || res.headers?.get("payment-response");

      return {
        ok: true,
        data: res.result,
        receipt: paymentReceipt || "Dev-Key Authorized",
      };
    } catch (err) {
      if (err.status === 402) {
        return {
          ok: false,
          paymentRequired: true,
          challenge: err.challenge,
          error: err.message,
        };
      }
      return {
        ok: false,
        error: err.message || String(err),
      };
    }
  }
}

class RaenCatalogService {
  constructor(catalogUrl = DEFAULT_CATALOG_URL, mcpClient) {
    this.catalogUrl = catalogUrl;
    this.mcpClient = mcpClient || new RaenMcpClient();
    this.cachedSkus = null;
    this.lastFetch = 0;
    this.cacheTtlMs = 60000;
  }

  parseLlmsTxt(content) {
    const lines = content.split("\n");
    const skus = [];
    let currentSection = "";

    for (const rawLine of lines) {
      const line = rawLine.trim();

      if (line.startsWith("## ")) {
        currentSection = line.replace(/^##\s+/, "").trim();
        continue;
      }

      const match = line.match(/^-\s*\[([^\]]+)\]\(([^)]+)\)\s*:\s*(.+)$/);
      if (match) {
        const [, name, url, description] = match;

        let category = "fleet-services";
        if (url.includes("workers.dev")) {
          category = "workers";
        } else if (currentSection.includes("Benchmark") || currentSection.includes("Company")) {
          category = "reference";
        }

        const priceMatch = description.match(/\$([0-9.]+)(?:\/[a-zA-Z]+|\s*USDC)?/);
        const price = priceMatch ? `$${priceMatch[1]}` : (category === "fleet-services" ? "$0.05" : "Free / Reference");

        skus.push({
          id: name.toLowerCase().replace(/[^a-z0-9_-]/g, "-"),
          name,
          url,
          price,
          category,
          description,
          manifestUrl: url.includes(".fly.dev") || url.includes("workers.dev") ? `${url.replace(/\/+$/, "")}/.well-known/x402.json` : undefined,
        });
      }
    }

    return skus;
  }

  async fetchCatalog(force = false) {
    const now = Date.now();
    if (!force && this.cachedSkus && now - this.lastFetch < this.cacheTtlMs) {
      return this.cachedSkus;
    }

    const allSkus = [];

    try {
      const tools = await this.mcpClient.listTools();
      for (const t of tools) {
        const price = t.description?.match(/\$([0-9.]+)/) ? `$${t.description.match(/\$([0-9.]+)/)[1]}` : "$0.05";
        allSkus.push({
          id: t.name,
          name: t.annotations?.title || t.name,
          url: `${this.mcpClient.getGatewayUrl()}#${t.name}`,
          price: `${price} USDC`,
          category: "mcp-tools",
          description: t.description,
          inputSchema: t.inputSchema,
        });
      }
    } catch {
      const standardTools = [
        { name: "raen_law_lookup", title: "Law Lookup (FCRA/FDCPA)", price: "$0.05 USDC", desc: "US consumer rights citations and statute research." },
        { name: "raen_ticker_analysis", title: "Ticker Consensus Demo", price: "$0.05 USDC", desc: "Synthetic market consensus demo via TradingAgents." },
        { name: "raen_dispute_letter", title: "Dispute Letter Generator", price: "$0.10 USDC", desc: "FCRA dispute letter generation + SVG certificate." },
        { name: "raen_image_generate", title: "NanoBanana Image Gen", price: "$0.01 USDC", desc: "Text-to-image AI generation." },
        { name: "raen_contract_analysis", title: "Contract Analysis", price: "$0.05 USDC", desc: "Contract risk scoring and clause-level review." },
      ];
      for (const st of standardTools) {
        allSkus.push({
          id: st.name,
          name: st.title,
          url: `${this.mcpClient.getGatewayUrl()}#${st.name}`,
          price: st.price,
          category: "mcp-tools",
          description: st.desc,
        });
      }
    }

    try {
      const resp = await fetch(this.catalogUrl, { signal: AbortSignal.timeout(10000) });
      if (resp.ok) {
        const text = await resp.text();
        const parsed = this.parseLlmsTxt(text);
        allSkus.push(...parsed);
      }
    } catch {
      // offline fallback
    }

    this.cachedSkus = allSkus;
    this.lastFetch = now;
    return allSkus;
  }
}

function generateCursorMcpConfig(apiKey, gatewayUrl) {
  const url = gatewayUrl || "https://raen-mcp-gateway.fly.dev/mcp";
  const config = {
    mcpServers: {
      raen: {
        url,
      },
    },
  };

  if (apiKey && apiKey.trim()) {
    config.mcpServers.raen.headers = {
      Authorization: `Bearer ${apiKey.trim()}`,
    };
  }

  return config;
}

let vscode;
try {
  vscode = require("vscode");
} catch {
  // Headless/test mode
}

class RaenSkuTreeDataProvider {
  constructor(catalogService) {
    this.catalogService = catalogService;
    if (vscode) {
      this._onDidChangeTreeData = new vscode.EventEmitter();
      this.onDidChangeTreeData = this._onDidChangeTreeData.event;
    }
  }

  refresh() {
    if (this._onDidChangeTreeData) {
      this._onDidChangeTreeData.fire(undefined);
    }
  }

  getTreeItem(element) {
    return element;
  }

  async getChildren(element) {
    if (!vscode) return [];

    if (!element) {
      return [
        new CategoryTreeItem("MCP Flagship Tools", "mcp-tools", vscode.TreeItemCollapsibleState.Expanded),
        new CategoryTreeItem("Production x402 Services", "fleet-services", vscode.TreeItemCollapsibleState.Collapsed),
        new CategoryTreeItem("Cloudflare Workers", "workers", vscode.TreeItemCollapsibleState.Collapsed),
        new CategoryTreeItem("Fleet Reference & Benchmark", "reference", vscode.TreeItemCollapsibleState.Collapsed),
      ];
    }

    if (element instanceof CategoryTreeItem) {
      const skus = await this.catalogService.fetchCatalog();
      const filtered = skus.filter((s) => s.category === element.categoryId);
      return filtered.map((sku) => new SkuTreeItem(sku));
    }

    return [];
  }
}

class CategoryTreeItem {
  constructor(label, categoryId, collapsibleState) {
    this.label = label;
    this.categoryId = categoryId;
    this.collapsibleState = collapsibleState;
    if (vscode) {
      this.iconPath = new vscode.ThemeIcon(
        categoryId === "mcp-tools" ? "tools" : categoryId === "fleet-services" ? "server" : "cloud"
      );
    }
  }
}

class SkuTreeItem {
  constructor(sku) {
    this.sku = sku;
    this.label = sku.name;
    this.description = sku.price;
    this.tooltip = `${sku.name}\n${sku.description}\nPrice: ${sku.price}\nURL: ${sku.url}`;
    if (vscode) {
      this.collapsibleState = vscode.TreeItemCollapsibleState.None;
      this.iconPath = new vscode.ThemeIcon(sku.category === "mcp-tools" ? "zap" : "globe");
      if (sku.id === "raen_law_lookup") {
        this.command = {
          command: "raen.runLawLookup",
          title: "Run Law Lookup",
          arguments: [sku],
        };
      }
    }
  }
}

function activate(context) {
  if (!vscode) return;

  const outputChannel = vscode.window.createOutputChannel("RAEN Fleet Output");
  outputChannel.appendLine("[RAEN] Initializing RAEN Fleet & MCP Tools extension...");

  const config = vscode.workspace.getConfiguration("raen");
  const apiKey = config.get("apiKey") || process.env.RAEN_API_KEY || "";
  const gatewayUrl = config.get("gatewayUrl") || "https://raen-mcp-gateway.fly.dev/mcp";
  const catalogUrl = config.get("catalogUrl") || "https://raw.githubusercontent.com/bshelby88/raen-agent-directory/main/llms.txt";

  const mcpClient = new RaenMcpClient(gatewayUrl, apiKey);
  const catalogService = new RaenCatalogService(catalogUrl, mcpClient);
  const treeDataProvider = new RaenSkuTreeDataProvider(catalogService);

  vscode.window.registerTreeDataProvider("raenSkuExplorer", treeDataProvider);

  const statusBar = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
  statusBar.text = apiKey ? "$(server) RAEN: Ready" : "$(server) RAEN: Set Dev Key";
  statusBar.tooltip = apiKey ? "RAEN MCP Gateway configured" : "Click to set RAEN Bearer dev key";
  statusBar.command = "raen.setApiKey";
  statusBar.show();
  context.subscriptions.push(statusBar);

  context.subscriptions.push(
    vscode.commands.registerCommand("raen.refreshCatalog", async () => {
      outputChannel.appendLine("[RAEN] Refreshing fleet catalog from llms.txt & MCP gateway...");
      await catalogService.fetchCatalog(true);
      treeDataProvider.refresh();
      vscode.window.showInformationMessage("RAEN Fleet catalog refreshed.");
    })
  );

  context.subscriptions.push(
    vscode.commands.registerCommand("raen.setApiKey", async () => {
      const key = await vscode.window.showInputBox({
        title: "RAEN MCP Gateway Dev Key",
        prompt: "Enter your Bearer key (request free key at https://raen-mcp-gateway.fly.dev/keys/request)",
        password: true,
        value: apiKey,
      });

      if (key !== undefined) {
        await config.update("apiKey", key, vscode.ConfigurationTarget.Global);
        mcpClient.setApiKey(key);
        statusBar.text = key ? "$(server) RAEN: Ready" : "$(server) RAEN: Set Dev Key";
        vscode.window.showInformationMessage("RAEN dev key updated.");
      }
    })
  );

  context.subscriptions.push(
    vscode.commands.registerCommand("raen.runLawLookup", async () => {
      const topic = await vscode.window.showInputBox({
        title: "RAEN Law Lookup (FCRA / FDCPA / TILA / UDAP)",
        prompt: "Enter consumer protection legal topic or citation question:",
        value: "debt collection calls at work under FDCPA",
      });

      if (!topic) return;

      outputChannel.show(true);
      outputChannel.appendLine(`\n------------------------------------------------------------`);
      outputChannel.appendLine(`[RAEN Tool Call] raen_law_lookup`);
      outputChannel.appendLine(`  Gateway URL : ${mcpClient.getGatewayUrl()}`);
      outputChannel.appendLine(`  Topic       : "${topic}"`);
      outputChannel.appendLine(`  Auth        : ${mcpClient.getApiKey() ? "Bearer key set" : "None (will receive 402 challenge)"}`);

      vscode.window.withProgress(
        {
          location: vscode.ProgressLocation.Notification,
          title: `Executing RAEN Law Lookup: ${topic}...`,
          cancellable: false,
        },
        async () => {
          try {
            const res = await mcpClient.callTool("raen_law_lookup", { topic });
            if (res.ok) {
              outputChannel.appendLine(`  Status      : SUCCESS (200 OK)`);
              outputChannel.appendLine(`  Receipt     : ${res.receipt}`);
              outputChannel.appendLine(`  Payload:\n${JSON.stringify(res.data, null, 2)}`);
              vscode.window.showInformationMessage(`RAEN Law Lookup completed for "${topic}". See Output Panel.`);
            } else if (res.paymentRequired) {
              outputChannel.appendLine(`  Status      : 402 PAYMENT REQUIRED`);
              outputChannel.appendLine(`  Challenge   :\n${JSON.stringify(res.challenge, null, 2)}`);
              outputChannel.appendLine(`  To execute paid tools, set your free dev key via 'RAEN: Set RAEN Gateway Dev Key'.`);
              vscode.window.showWarningMessage(
                "RAEN 402 Payment Challenge received: $0.05 USDC on Base. Set a dev key via command 'RAEN: Set RAEN Gateway Dev Key'."
              );
            } else {
              outputChannel.appendLine(`  Error       : ${res.error}`);
              vscode.window.showErrorMessage(`RAEN Tool Error: ${res.error}`);
            }
          } catch (err) {
            outputChannel.appendLine(`  Exception   : ${err.message}`);
            vscode.window.showErrorMessage(`Execution failed: ${err.message}`);
          }
        }
      );
    })
  );

  context.subscriptions.push(
    vscode.commands.registerCommand("raen.runContractAnalyze", async () => {
      const editor = vscode.window.activeTextEditor;
      let text = editor?.document.getText(editor.selection);

      if (!text || text.length < 40) {
        text = await vscode.window.showInputBox({
          title: "RAEN Contract Analysis (Contract-Eye)",
          prompt: "Paste contract clause or agreement snippet to audit (min 40 chars):",
        });
      }

      if (!text || text.length < 40) {
        vscode.window.showWarningMessage("Contract text must be at least 40 characters.");
        return;
      }

      outputChannel.show(true);
      outputChannel.appendLine(`\n------------------------------------------------------------`);
      outputChannel.appendLine(`[RAEN Tool Call] raen_contract_analysis`);
      outputChannel.appendLine(`  Text Length : ${text.length} characters`);

      vscode.window.withProgress(
        {
          location: vscode.ProgressLocation.Notification,
          title: `Auditing contract with RAEN Contract-Eye...`,
          cancellable: false,
        },
        async () => {
          const res = await mcpClient.callTool("raen_contract_analysis", { text });
          if (res.ok) {
            outputChannel.appendLine(`  Status      : SUCCESS`);
            outputChannel.appendLine(`  Receipt     : ${res.receipt}`);
            outputChannel.appendLine(`  Result:\n${JSON.stringify(res.data, null, 2)}`);
            vscode.window.showInformationMessage("Contract audit completed. Check output channel.");
          } else if (res.paymentRequired) {
            outputChannel.appendLine(`  Status      : 402 PAYMENT REQUIRED`);
            outputChannel.appendLine(`  Challenge   :\n${JSON.stringify(res.challenge, null, 2)}`);
            vscode.window.showWarningMessage("RAEN 402 Payment Challenge: Set dev key via 'RAEN: Set RAEN Gateway Dev Key'.");
          } else {
            outputChannel.appendLine(`  Error       : ${res.error}`);
            vscode.window.showErrorMessage(`Audit failed: ${res.error}`);
          }
        }
      );
    })
  );

  context.subscriptions.push(
    vscode.commands.registerCommand("raen.configureCursorMcp", async () => {
      const configJson = generateCursorMcpConfig(apiKey, gatewayUrl);
      const formatted = JSON.stringify(configJson, null, 2);

      const choice = await vscode.window.showInformationMessage(
        "Generate RAEN Cursor MCP Configuration (.cursor/mcp.json)?",
        "Write to Workspace",
        "Copy to Clipboard"
      );

      if (choice === "Copy to Clipboard") {
        await vscode.env.clipboard.writeText(formatted);
        vscode.window.showInformationMessage("Copied Cursor MCP configuration to clipboard!");
      } else if (choice === "Write to Workspace") {
        const workspaceFolders = vscode.workspace.workspaceFolders;
        if (!workspaceFolders || workspaceFolders.length === 0) {
          vscode.window.showErrorMessage("No open workspace to write .cursor/mcp.json.");
          return;
        }

        const cursorDirUri = vscode.Uri.joinPath(workspaceFolders[0].uri, ".cursor");
        const mcpFileUri = vscode.Uri.joinPath(cursorDirUri, "mcp.json");

        try {
          await vscode.workspace.fs.createDirectory(cursorDirUri);
          const encoder = new TextEncoder();
          await vscode.workspace.fs.writeFile(mcpFileUri, encoder.encode(formatted));
          vscode.window.showInformationMessage("Successfully created .cursor/mcp.json with RAEN MCP Gateway!");
        } catch (err) {
          vscode.window.showErrorMessage(`Failed writing .cursor/mcp.json: ${err.message}`);
        }
      }
    })
  );

  outputChannel.appendLine("[RAEN] Extension ready. Explore SKUs in the 'RAEN Fleet' activity bar pane.");
}

function deactivate() {}

function generateOneLiner(apiKey, gatewayUrl) {
  const cfg = generateCursorMcpConfig(apiKey, gatewayUrl);
  return JSON.stringify(cfg, null, 2);
}

module.exports = {
  RaenMcpClient,
  RaenCatalogService,
  generateCursorMcpConfig,
  generateOneLiner,
  RaenSkuTreeDataProvider,
  activate,
  deactivate,
};
