import { RaenCatalogService } from "./catalog.js";
import { generateCursorMcpConfig } from "./cursorConfig.js";
import { RaenMcpClient } from "./mcpClient.js";
import type { RaenSku } from "./types.js";

// Minimal VS Code typings fallback if vscode is loaded dynamically
let vscode: any;
try {
  vscode = await import("vscode");
} catch {
  // Headless test environment
}

export class RaenSkuTreeDataProvider {
  private _onDidChangeTreeData: any;
  public readonly onDidChangeTreeData: any;
  private catalogService: RaenCatalogService;

  constructor(catalogService: RaenCatalogService) {
    this.catalogService = catalogService;
    if (vscode) {
      this._onDidChangeTreeData = new vscode.EventEmitter();
      this.onDidChangeTreeData = this._onDidChangeTreeData.event;
    }
  }

  public refresh(): void {
    if (this._onDidChangeTreeData) {
      this._onDidChangeTreeData.fire(undefined);
    }
  }

  public getTreeItem(element: any): any {
    return element;
  }

  public async getChildren(element?: any): Promise<any[]> {
    if (!vscode) return [];

    if (!element) {
      // Top-level categories
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
  public label: string;
  public categoryId: string;
  public collapsibleState: any;
  public iconPath: any;

  constructor(label: string, categoryId: string, collapsibleState: any) {
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
  public label: string;
  public description: string;
  public tooltip: string;
  public sku: RaenSku;
  public collapsibleState: any;
  public iconPath: any;
  public command?: any;

  constructor(sku: RaenSku) {
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

export function activate(context: any): void {
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

  // Status Bar Item
  const statusBar = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
  statusBar.text = apiKey ? "$(server) RAEN: Ready" : "$(server) RAEN: Set Dev Key";
  statusBar.tooltip = apiKey ? "RAEN MCP Gateway configured" : "Click to set RAEN Bearer dev key";
  statusBar.command = "raen.setApiKey";
  statusBar.show();
  context.subscriptions.push(statusBar);

  // Command: Refresh Catalog
  context.subscriptions.push(
    vscode.commands.registerCommand("raen.refreshCatalog", async () => {
      outputChannel.appendLine("[RAEN] Refreshing fleet catalog from llms.txt & MCP gateway...");
      await catalogService.fetchCatalog(true);
      treeDataProvider.refresh();
      vscode.window.showInformationMessage("RAEN Fleet catalog refreshed.");
    })
  );

  // Command: Set API Key
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

  // Command: Run Law Lookup
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
          } catch (err: any) {
            outputChannel.appendLine(`  Exception   : ${err.message}`);
            vscode.window.showErrorMessage(`Execution failed: ${err.message}`);
          }
        }
      );
    })
  );

  // Command: Run Contract Analyze
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

  // Command: Configure Cursor MCP Server
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
        } catch (err: any) {
          vscode.window.showErrorMessage(`Failed writing .cursor/mcp.json: ${err.message}`);
        }
      }
    })
  );

  outputChannel.appendLine("[RAEN] Extension ready. Explore SKUs in the 'RAEN Fleet' activity bar pane.");
}

export function deactivate(): void {}
