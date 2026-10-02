import{c as m}from"./chunk-JC2BH436.js";var v=class{get baseUrl(){let e=document.querySelector("[data-clew-config]"),t=document.querySelector('meta[name="stx-mount"]'),i=e?.dataset.mount??t?.content;if(i===void 0)throw new Error("Clew mount configuration is missing");if(i&&(!i.startsWith("/")||i.startsWith("//")||/[?#\\]/.test(i)))throw new Error("Clew mount configuration is invalid");return`${i.replace(/\/+$/,"")}/api`}fileContentUrl(e,t=!1){let i=this.requestUrl("/file/");return i.searchParams.set("path",e),t&&i.searchParams.set("raw","true"),i.toString()}requestUrl(e){let t=new URL(`${this.baseUrl}${e}`,window.location.origin),i=document.getElementById("workspace-project-config"),n=i?.dataset.username,a=i?.dataset.projectSlug,r=new URLSearchParams(window.location.search).get("project"),c=i?.dataset.projectRef||(n&&a?`${n}/${a}`:r);return c&&t.searchParams.set("project",c),t}getCsrf(){let e=document.cookie.match(/csrftoken=([^;]+)/);return e?e[1]:""}async fetchJson(e,t,i="GET"){try{let n=this.requestUrl(e);i==="GET"&&t&&Object.entries(t).forEach(([u,w])=>n.searchParams.append(u,w));let a=i==="POST"?{method:"POST",headers:{"Content-Type":"application/json","X-CSRFToken":this.getCsrf()},body:JSON.stringify(t??{})}:{};return await(await fetch(n.toString(),a)).json()}catch(n){return{success:!1,error:n instanceof Error?n.message:"Unknown error occurred"}}}async getStatus(){return this.fetchJson("/status/")}async getStats(){return this.fetchJson("/stats/")}async listRuns(e){let t={};return e?.limit!==void 0&&(t.limit=e.limit.toString()),e?.offset!==void 0&&(t.offset=e.offset.toString()),e?.status&&(t.status=e.status),this.fetchJson("/runs/",t)}async verifyRun(e,t=!1){return this.fetchJson("/verify-run/",{session_id:e,from_scratch:t.toString()})}async verifyChain(e){return this.fetchJson("/verify-chain/",{target:e})}async getDagJson(e){let t={};return e?.sessionId&&(t.session_id=e.sessionId),e?.targetFile&&(t.target_file=e.targetFile),e?.pathMode&&(t.path_mode=e.pathMode),this.fetchJson("/dag/json/",t)}async getMermaidDag(e){let t={};return e?.sessionId&&(t.session_id=e.sessionId),e?.targetFile&&(t.target_file=e.targetFile),e?.targetFiles?.length&&(t.target_files=e.targetFiles.join(",")),e?.claims&&(t.claims="true"),e?.showHashes!==void 0&&(t.show_hashes=e.showHashes.toString()),e?.pathMode&&(t.path_mode=e.pathMode),this.fetchJson("/dag/mermaid/",t)}async listClaims(e){let t={};return e?.filePath&&(t.file_path=e.filePath),e?.claimType&&(t.claim_type=e.claimType),e?.status&&(t.status=e.status),e?.limit!==void 0&&(t.limit=e.limit.toString()),this.fetchJson("/claims/",t)}async addExamples(){return this.fetchJson("/add-examples/",{},"POST")}},o=new v;async function P(){let{default:s}=await import("./mermaid.core-M4KZ4NA5.js");return s.initialize({startOnLoad:!1,theme:document.documentElement.dataset.theme==="dark"?"dark":"default",securityLevel:"strict",flowchart:{curve:"basis"}}),s}async function l(s,e){let t=e.trim();if(!t||t==="graph TD")return d(s,"Empty diagram"),!1;let i="mermaid-dag-"+Date.now(),n=document.createElement("div");n.className="dag-mermaid-wrapper";let a=document.createElement("div");a.className="mermaid",a.id=i,a.textContent=t,n.appendChild(a),s.innerHTML="",s.appendChild(n);try{return await(await P()).run({nodes:[n.querySelector(".mermaid")]}),A(n),!0}catch(r){console.error("[Clew] Mermaid render error:",r);let c=document.createElement("pre");return c.className="dag-mermaid-code",c.textContent=t,n.replaceChildren(c),!1}}function x(s,e,t){let i=o.fileContentUrl(e,!0);s.innerHTML=`
    <div class="dag-mermaid-wrapper">
      <img src="${i}" alt="Clew DAG" style="max-width:100%;height:auto;" />
    </div>
  `}async function g(s,e){try{let t=o.fileContentUrl(s),i=await fetch(t);if(!i.ok)return null;let n=await i.json();return n.success&&n.content?n.content:null}catch{return null}}function b(s,e,t,i){s.innerHTML=`
    <div class="dag-placeholder">
      <i class="fas ${e} fa-3x"></i>
      <h3>${t}</h3>
      <p></p>
    </div>
  `,s.querySelector("p").textContent=i}function p(s){s.innerHTML=`
    <div class="dag-placeholder">
      <i class="fas fa-spinner fa-spin fa-3x"></i>
      <h3>Loading...</h3>
      <p>Fetching verification data</p>
    </div>
  `}function d(s,e){s.innerHTML=`
    <div class="dag-placeholder">
      <i class="fas fa-exclamation-triangle fa-3x"></i>
      <h3>Error</h3>
      <p></p>
    </div>
  `,s.querySelector("p").textContent=e}function y(s){let e={verified:'<span class="badge badge-success">Verified</span>',mismatch:'<span class="badge badge-danger">Mismatch</span>',missing:'<span class="badge badge-warning">Missing</span>',unknown:'<span class="badge badge-secondary">Unknown</span>'};return e[s]||e.unknown}function A(s){s.querySelectorAll(".node").forEach(t=>{t.style.cursor="pointer",t.addEventListener("click",()=>{let i=t.querySelector(".nodeLabel")?.textContent?.trim();i&&document.dispatchEvent(new CustomEvent("fileSelected",{detail:{path:i}}))})})}function E(s){let e=s.dataTransfer?.getData("application/x-scitex-file");if(e)try{let i=JSON.parse(e);if(Array.isArray(i))return i.map(n=>n.path||n);if(i.path)return[i.path]}catch{}let t=s.dataTransfer?.getData("text/plain");return t?t.split(";").filter(Boolean):[]}async function _(s,e){p(s);let t=await o.getMermaidDag({targetFiles:e,pathMode:"name"});t.success&&t.data?.mermaid?await l(s,t.data.mermaid):d(s,t.error||`No verification data for ${e.length} files`)}async function f(s,e,t,i){if(e.endsWith(".mmd")){let u=await g(e,t);u?await l(s,u):d(s,`Could not load ${e}`);return}let n=await g(`${e}-clew.mmd`,t);if(n){await l(s,n);return}let a=`${e}-clew.png`;if(await g(a,t)!==null){x(s,a,t);return}let c=await o.getStats();if(c.success&&c.data&&c.data.total_runs>0){await k(s,e,i);return}console.log("[Clew] No companion files or runs for:",e)}async function k(s,e,t){p(s);let i=await o.verifyChain(e);if(i.success&&i.data){let n=await o.getMermaidDag({targetFile:e,pathMode:"name"});n.success&&n.data?.mermaid&&await l(s,n.data.mermaid),j(t,i.data)}else d(s,i.error||"Failed to load verification chain")}function j(s,e){if(!s)return;let t=`
    <div class="chain-details">
      <h4>Verification Chain</h4>
      <p><strong>Target:</strong> ${e.target_file}</p>
      <p><strong>Status:</strong> ${y(e.status)}</p>
      <p><strong>Runs:</strong> ${e.runs.length}</p>
    </div>
  `;t+='<div class="runs-list">',e.runs.forEach((i,n)=>{t+=`
      <div class="run-item">
        <h5>Run ${n+1}: ${i.session_id.substring(0,12)}...</h5>
        <p><strong>Script:</strong> ${i.script_path||"Unknown"}</p>
        <p><strong>Status:</strong> ${y(i.status)}</p>
        <p><strong>Files:</strong> ${i.files.length}</p>
      </div>
    `}),t+="</div>",s.innerHTML=t}function T(s,e){let t=document.getElementById("clewModeSelector");t&&t.addEventListener("click",i=>{let n=i.target.closest(".clew-tab");if(!n)return;let a=n.dataset.mode;a&&a!==e()&&s(a)})}function h(s){let e=document.getElementById("clewModeSelector");e&&(e.querySelectorAll(".clew-tab").forEach(t=>{t.classList.toggle("active",t.dataset.mode===s)}),F(s))}var I={project:"Visualizes the full verification DAG for all tracked runs. Each node shows a script or file with its SHA-256 hash status \u2014 green means verified, red means the file has changed since it was recorded.",file:"Drop or select any output file from the file tree to trace its full dependency chain back to the original source data. Multiple files merge into a single DAG.",claims:"Links specific manuscript assertions (statistics, figures, tables) to the scripts and data that produced them. Define the manuscript claims before verification."};function F(s){let e=document.getElementById("clewModeInfo");e&&(e.innerHTML=I[s]??"")}function $(s,e){let t=document.querySelector(".pane-header-actions");if(!t)return;let i=t.querySelector(".clew-db-badge");i&&i.remove();let n=document.createElement("span");n.className=`clew-db-badge ${s?"clew-db-badge--found":"clew-db-badge--missing"}`;let a=s?"Records available":"Records unavailable",r=e?`${s?"Database":"Expected"}: ${e}`:"No project database";n.title=r,n.innerHTML=`<i class="fas fa-database"></i> ${a}`,t.appendChild(n)}async function C(s,e){let t=await o.getStats();if(!t.success){d(s,t.error||"Project records are unavailable");return}if(t.success&&t.data&&$(t.data.db_found??!1,t.data.db_path??null),t.success&&t.data&&t.data.total_runs>0){p(s);let n=await o.getMermaidDag({pathMode:"name"});if(n.success&&n.data?.mermaid){await l(s,n.data.mermaid);return}}let i=t.data;i&&i.total_runs>0?s.innerHTML=`
      <div class="dag-placeholder">
        <h3>DAG Visualization</h3>
        <p>${i.total_runs} runs tracked</p>
      </div>
    `:s.innerHTML=`
      <div class="dag-placeholder clew-empty-state">
        <h3>No Runs Yet</h3>
        <p class="clew-empty-subtitle">Clew tracks every script run \u2014 recording inputs, outputs, and their SHA-256 hashes \u2014 then visualizes the full dependency DAG so you can verify reproducibility at any time.</p>
        <div class="clew-instructions clew-instructions-vertical">
          <div class="clew-direction clew-direction-code">
            <h4><i class="fas fa-code"></i> Example Script</h4>
            <pre data-language="python"><code class="language-python">import scitex

@scitex.session
def main():
    data = scitex.io.load("raw_data.csv")
    result = data.groupby("condition").mean()
    scitex.io.save(result, "summary.csv")

    fig, ax = scitex.plt.subplots()
    ax.plot_line(result.index, result.values)
    scitex.io.save(fig, "figure_1.png")</code></pre>
          </div>
          <div class="clew-direction clew-direction-start">
            <h4><i class="fas fa-rocket"></i> Quick Start</h4>
            <ol>
              <li>
                <button class="clew-add-examples-btn btn btn-sm btn-outline-primary">Add Examples</button>
                to load example scripts into this project
              </li>
              <li>Run from project root:
                <pre data-language="bash"><code class="language-bash">bash ./examples/clew/00_run_all.sh</code></pre>
              </li>
              <li>Switch to <strong>Project</strong> mode to view the DAG</li>
            </ol>
            <div class="clew-features">
              <div class="clew-feature">
                <code>scitex.io</code>
                <span>30+ formats (CSV, NumPy, images, pickle, etc.)</span>
              </div>
              <div class="clew-feature">
                <code>scitex.plt</code>
                <span>Publication-ready figures with auto CSV export</span>
              </div>
              <div class="clew-feature">
                <code>scitex.clew</code>
                <span>SHA-256 hashed dependency DAG</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    `}async function S(s){p(s);let[e,t]=await Promise.all([o.listClaims(),o.getMermaidDag({claims:!0,pathMode:"name"})]);if(!e.success||!t.success){d(s,e.error||t.error||"Claim records are unavailable");return}t.success&&t.data?.mermaid&&t.data.mermaid.trim()!=="graph TD"?await l(s,t.data.mermaid):b(s,"fa-file-contract","No Claims Registered","Claims link specific manuscript assertions (statistics, figures, tables) to the source data and scripts that produced them. Define the manuscript claims before verification."),e.success&&e.data?.claims?.length&&q(s,e.data.claims)}function L(s){let e=document.createElement("span");return e.textContent=s,e.innerHTML}function q(s,e){let t={statistic:"fa-chart-bar",figure:"fa-image",table:"fa-table",text:"fa-font",value:"fa-hashtag"},i={registered:'<span class="badge badge-secondary">Registered</span>',verified:'<span class="badge badge-success">Verified</span>',mismatch:'<span class="badge badge-danger">Mismatch</span>',missing:'<span class="badge badge-warning">Missing</span>',partial:'<span class="badge badge-warning">Partial</span>'},n=e.map(r=>{let c=t[r.claim_type]||"fa-question",u=r.line_number?`${r.file_path.split("/").pop()}:L${r.line_number}`:r.file_path.split("/").pop(),w=r.claim_value?` = ${r.claim_value}`:"",R=i[r.status]||i.registered;return`<div class="claim-item">
        <i class="fas ${c} claim-type-icon"></i>
        <span class="claim-location">${L(u||"")}</span>
        <span class="claim-value">${L(w)}</span>
        ${R}
      </div>`}).join(""),a=document.createElement("div");a.className="claims-list",a.innerHTML=n,s.appendChild(a)}function D(s){b(s,"fa-crosshairs","File Trace Mode","Select any output file to trace its full dependency chain back to the original source data as a DAG. Each node shows the script and hash status \u2014 green means verified, red means the file has changed since it was recorded. Drop multiple files to see a merged DAG.")}var M=class{constructor(){m(this,"dagArea",null);m(this,"detailsPanel",null);m(this,"projectId",null);m(this,"currentMode","project");this.dagArea=document.querySelector(".dag-visualization-area"),this.detailsPanel=document.querySelector(".clew-details-content"),this.extractProjectInfo()}extractProjectInfo(){let e=document.getElementById("workspace-project-config");e&&(this.projectId=e.dataset.projectRef||e.dataset.projectId||null)}async initialize(){if(!this.projectId){console.log("[Clew] No project selected");return}T(i=>{this.currentMode=i,h(i),this.renderCurrentMode()},()=>this.currentMode),h(this.currentMode),document.getElementById("clew-file-form")?.addEventListener("submit",i=>{i.preventDefault();let n=document.querySelector("#clew-file-path")?.value.trim();n&&document.dispatchEvent(new CustomEvent("fileSelected",{detail:{path:n}}))}),this.setupEventListeners(),this.setupDropTarget();let t=new URLSearchParams(window.location.search).get("file");t?(this.switchToFileMode(),this.dagArea&&await f(this.dagArea,t,this.projectId,this.detailsPanel)):await this.renderCurrentMode()}switchToFileMode(){this.currentMode="file",h("file")}async renderCurrentMode(){if(this.dagArea){switch(this.currentMode){case"project":await C(this.dagArea,this.projectId);break;case"claims":await S(this.dagArea);break;case"file":D(this.dagArea);break}this.updateAddExamplesVisibility()}}updateAddExamplesVisibility(){if(!this.dagArea)return;let e=this.dagArea.querySelector(".clew-add-examples-btn");e&&e.addEventListener("click",()=>this.addExamples(e))}async addExamples(e){e.disabled=!0,e.innerHTML="Adding...";let t=await o.addExamples();t.success?(e.innerHTML="Added",this.showExamplesGuidance(),e.style.display="none"):(e.innerHTML="Add Examples",e.disabled=!1,console.error("[Clew] Failed to add examples:",t.error),alert(`Failed to add examples: ${t.error}`))}showExamplesGuidance(){this.dagArea&&(this.dagArea.innerHTML=`
      <div class="dag-placeholder">
        <i class="fas fa-check-circle fa-3x"></i>
        <h3>Examples Ready</h3>
        <p>Example scripts added to <code>examples/clew/</code></p>
        <div class="clew-instructions" style="margin-top:1rem;">
          <div class="clew-direction">
            <h4>Step 1: Run the examples</h4>
            <p>Open a terminal and run:</p>
            <pre><code>cd examples/clew
bash 00_run_all.sh</code></pre>
          </div>
          <div class="clew-direction">
            <h4>Step 2: View the DAG</h4>
            <p>After running, click <strong>Project</strong> to see the full verification DAG.</p>
            <pre><code>scitex clew list
scitex clew status</code></pre>
          </div>
        </div>
      </div>
    `)}setupEventListeners(){document.addEventListener("fileSelected",async e=>{let i=e.detail?.path;i&&this.dagArea&&(this.switchToFileMode(),await f(this.dagArea,i,this.projectId,this.detailsPanel))})}setupDropTarget(){this.dagArea&&(this.dagArea.addEventListener("dragover",e=>{e.preventDefault(),e.stopPropagation(),this.dagArea.classList.add("drop-target"),e.dataTransfer&&(e.dataTransfer.dropEffect="copy")}),this.dagArea.addEventListener("dragleave",e=>{e.preventDefault(),this.dagArea.classList.remove("drop-target")}),this.dagArea.addEventListener("drop",async e=>{e.preventDefault(),e.stopPropagation(),this.dagArea.classList.remove("drop-target");let t=E(e);t.length!==0&&(this.switchToFileMode(),t.length>1?await _(this.dagArea,t):await f(this.dagArea,t[0],this.projectId,this.detailsPanel))}))}};function H(){new M().initialize()}document.readyState==="loading"?document.addEventListener("DOMContentLoaded",H):H();
