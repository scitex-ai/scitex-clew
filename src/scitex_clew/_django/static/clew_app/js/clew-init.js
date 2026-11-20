import{a as M}from"./chunk-6CNQY6Z3.js";import{c as g}from"./chunk-JC2BH436.js";var b=class{get baseUrl(){let e=document.querySelector("[data-clew-config]"),t=document.querySelector('meta[name="stx-mount"]'),i=e?.dataset.mount??t?.content;if(i===void 0)throw new Error("Clew mount configuration is missing");if(i&&(!i.startsWith("/")||i.startsWith("//")||/[?#\\]/.test(i)))throw new Error("Clew mount configuration is invalid");return`${i.replace(/\/+$/,"")}/api`}fileContentUrl(e,t=!1){let i=this.requestUrl("/file/");return i.searchParams.set("path",e),t&&i.searchParams.set("raw","true"),i.toString()}requestUrl(e){let t=new URL(`${this.baseUrl}${e}`,window.location.origin),i=document.getElementById("workspace-project-config"),n=i?.dataset.username,r=i?.dataset.projectSlug,o=new URLSearchParams(window.location.search).get("project"),a=i?.dataset.projectRef||(n&&r?`${n}/${r}`:o);return a&&t.searchParams.set("project",a),t}getCsrf(){let e=document.cookie.match(/csrftoken=([^;]+)/);return e?e[1]:""}async fetchJson(e,t,i="GET"){try{let n=this.requestUrl(e);i==="GET"&&t&&Object.entries(t).forEach(([c,l])=>n.searchParams.append(c,l));let r=i==="POST"?{method:"POST",headers:{"Content-Type":"application/json","X-CSRFToken":this.getCsrf()},body:JSON.stringify(t??{})}:{};return await(await fetch(n.toString(),r)).json()}catch(n){return{success:!1,error:n instanceof Error?n.message:"Unknown error occurred"}}}async getStatus(){return this.fetchJson("/status/")}async getStats(){return this.fetchJson("/stats/")}async listRuns(e){let t={};return e?.limit!==void 0&&(t.limit=e.limit.toString()),e?.offset!==void 0&&(t.offset=e.offset.toString()),e?.status&&(t.status=e.status),this.fetchJson("/runs/",t)}async verifyRun(e,t=!1){return this.fetchJson("/verify-run/",{session_id:e,from_scratch:t.toString()})}async verifyChain(e){return this.fetchJson("/verify-chain/",{target:e})}async getDagJson(e){let t={};return e?.sessionId&&(t.session_id=e.sessionId),e?.targetFile&&(t.target_file=e.targetFile),e?.pathMode&&(t.path_mode=e.pathMode),this.fetchJson("/dag/json/",t)}async getMermaidDag(e){let t={};return e?.sessionId&&(t.session_id=e.sessionId),e?.targetFile&&(t.target_file=e.targetFile),e?.targetFiles?.length&&(t.target_files=e.targetFiles.join(",")),e?.claims&&(t.claims="true"),e?.showHashes!==void 0&&(t.show_hashes=e.showHashes.toString()),e?.pathMode&&(t.path_mode=e.pathMode),this.fetchJson("/dag/mermaid/",t)}async listClaims(e){let t={};return e?.filePath&&(t.file_path=e.filePath),e?.claimType&&(t.claim_type=e.claimType),e?.status&&(t.status=e.status),e?.limit!==void 0&&(t.limit=e.limit.toString()),this.fetchJson("/claims/",t)}async addExamples(){return this.fetchJson("/add-examples/",{},"POST")}},d=new b;function _(s,e,t){if(["fill","stroke","color","stop-color"].includes(s))return e==="none"||!/(?:url|var|env|expression)\s*\(|\\/i.test(e)&&CSS.supports("color",e);if(["marker-start","marker-mid","marker-end","clip-path","filter"].includes(s)){if(e==="none")return!0;let n=/^url\(["']?#([\w:-]+)["']?\)$/.exec(e);return!!n&&t.has(n[1])}return["opacity","fill-opacity","stroke-opacity"].includes(s)?/^(?:0(?:\.\d+)?|1(?:\.0+)?)$/.test(e):["font-size","stroke-width","letter-spacing","width","height","max-width","max-height"].includes(s)?/^\d+(?:\.\d+)?(?:px|pt|em|rem|%)?$/.test(e):s==="stroke-dasharray"?/^[\d.,\s]+$/.test(e)||e==="none":s==="font-family"?/^[\w\s,\-"']+$/.test(e):{"font-weight":["normal","bold","100","200","300","400","500","600","700","800","900"],"font-style":["normal","italic","oblique"],"text-anchor":["start","middle","end"],"dominant-baseline":["auto","middle","central","hanging","alphabetic"],"stroke-linecap":["butt","round","square"],"stroke-linejoin":["miter","round","bevel"],"white-space":["normal","pre","pre-wrap"]}[s]?.includes(e)??!1}function E(s,e,t){for(let i=0;i<e.length;i++){let n=e.item(i),r=e.getPropertyValue(n).trim();_(n,r,t)&&s.style.setProperty(n,r)}}function C(s){let t=M.sanitize(s,{USE_PROFILES:{svg:!0,svgFilters:!0},RETURN_DOM_FRAGMENT:!0,FORBID_TAGS:["script","foreignObject","a","image","use","animate","animateMotion","animateTransform","set","feImage"],FORBID_ATTR:["href","xlink:href","src"]}).querySelector("svg");if(!(t instanceof SVGSVGElement))throw new Error("Diagram contains no SVG");let i=new Set(Array.from(t.querySelectorAll("[id]"),a=>a.id));i.add(t.id);let n=[t,...t.querySelectorAll("*")],r=n.map(a=>[a,a.getAttribute("style")]),o=Array.from(t.querySelectorAll("style"),a=>a.textContent??"");t.querySelectorAll("style").forEach(a=>a.remove());for(let a of n){a.removeAttribute("style");for(let c of["fill","stroke","filter","clip-path","marker-start","marker-mid","marker-end"]){let l=a.getAttribute(c);l!==null&&!_(c,l,i)&&a.removeAttribute(c)}}for(let a of o){let c=new CSSStyleSheet;c.replaceSync(a);for(let l of c.cssRules)if(l instanceof CSSStyleRule)try{t.matches(l.selectorText)&&E(t,l.style,i);for(let p of t.querySelectorAll(l.selectorText))E(p,l.style,i)}catch{}}for(let[a,c]of r){if(!c)continue;let l=new CSSStyleSheet;l.replaceSync(`x { ${c} }`);let p=l.cssRules[0];p instanceof CSSStyleRule&&E(a,p.style,i)}return t}async function j(){let{default:s}=await import("./mermaid.core-OYY6YZ7M.js");return s.initialize({startOnLoad:!1,theme:document.documentElement.dataset.theme==="dark"||document.documentElement.classList.contains("dark-mode")?"dark":"default",securityLevel:"strict",htmlLabels:!1,flowchart:{curve:"basis",htmlLabels:!1}}),s}async function u(s,e){let t=e.trim();if(!t||t==="graph TD")return m(s,"Empty diagram"),!1;let i="mermaid-dag-"+Date.now(),n=document.createElement("div");n.className="dag-mermaid-wrapper",n.textContent="Rendering diagram\u2026",s.replaceChildren(),s.appendChild(n);try{let r=await j(),{svg:o}=await r.render(i,t);return n.replaceChildren(C(o)),F(n),!0}catch(r){console.error("[Clew] Mermaid render error:",r);let o=document.createElement("pre");return o.className="dag-mermaid-code",o.textContent=t,n.replaceChildren(o),!1}}function L(s,e,t){let i=d.fileContentUrl(e,!0),n=document.createElement("div");n.className="dag-mermaid-wrapper";let r=document.createElement("img");r.src=i,r.alt="Clew DAG",r.style.maxWidth="100%",r.style.height="auto",n.append(r),s.replaceChildren(n)}async function h(s,e){try{let t=d.fileContentUrl(s),i=await fetch(t);if(!i.ok)return null;let n=await i.json();return n.success&&n.content?n.content:null}catch{return null}}function w(s,e,t,i){let n=document.createElement("div");n.className="dag-placeholder";let r=document.createElement("i");r.className=`fas ${e} fa-3x`;let o=document.createElement("h3");o.textContent=t;let a=document.createElement("p");a.textContent=i,n.append(r,o,a),s.replaceChildren(n)}function f(s){s.innerHTML=`
    <div class="dag-placeholder">
      <i class="fas fa-spinner fa-spin fa-3x"></i>
      <h3>Loading...</h3>
      <p>Fetching verification data</p>
    </div>
  `}function m(s,e){w(s,"fa-exclamation-triangle","Error",e)}function x(s){let e={verified:'<span class="badge badge-success">Verified</span>',mismatch:'<span class="badge badge-danger">Mismatch</span>',missing:'<span class="badge badge-warning">Missing</span>',unknown:'<span class="badge badge-secondary">Unknown</span>'};return e[s]||e.unknown}function F(s){s.querySelectorAll(".node").forEach(t=>{t.style.cursor="pointer",t.addEventListener("click",()=>{let i=(t.querySelector(".nodeLabel")??t.querySelector(".label"))?.textContent?.trim();i&&document.dispatchEvent(new CustomEvent("fileSelected",{detail:{path:i}}))})})}function T(s){let e=s.dataTransfer?.getData("application/x-scitex-file");if(e)try{let i=JSON.parse(e);if(Array.isArray(i))return i.map(n=>n.path||n);if(i.path)return[i.path]}catch{}let t=s.dataTransfer?.getData("text/plain");return t?t.split(";").filter(Boolean):[]}async function D(s,e){f(s);let t=await d.getMermaidDag({targetFiles:e,pathMode:"name"});t.success&&t.data?.mermaid?await u(s,t.data.mermaid):m(s,t.error||`No verification data for ${e.length} files`)}async function v(s,e,t,i){if(e.endsWith(".mmd")){let c=await h(e,t);c?await u(s,c):m(s,`Could not load ${e}`);return}let n=await h(`${e}-clew.mmd`,t);if(n){await u(s,n);return}let r=`${e}-clew.png`;if(await h(r,t)!==null){L(s,r,t);return}let a=await d.getStats();if(a.success&&a.data&&a.data.total_runs>0){await $(s,e,i);return}console.log("[Clew] No companion files or runs for:",e)}async function $(s,e,t){f(s);let i=await d.verifyChain(e);if(i.success&&i.data){let n=await d.getMermaidDag({targetFile:e,pathMode:"name"});n.success&&n.data?.mermaid&&await u(s,n.data.mermaid),V(t,i.data)}else m(s,i.error||"Failed to load verification chain")}function V(s,e){if(!s)return;let t=`
    <div class="chain-details">
      <h4>Verification Chain</h4>
      <p><strong>Target:</strong> ${e.target_file}</p>
      <p><strong>Status:</strong> ${x(e.status)}</p>
      <p><strong>Runs:</strong> ${e.runs.length}</p>
    </div>
  `;t+='<div class="runs-list">',e.runs.forEach((i,n)=>{t+=`
      <div class="run-item">
        <h5>Run ${n+1}: ${i.session_id.substring(0,12)}...</h5>
        <p><strong>Script:</strong> ${i.script_path||"Unknown"}</p>
        <p><strong>Status:</strong> ${x(i.status)}</p>
        <p><strong>Files:</strong> ${i.files.length}</p>
      </div>
    `}),t+="</div>",s.innerHTML=t}function A(s,e){let t=document.getElementById("clewModeSelector");t&&t.addEventListener("click",i=>{let n=i.target.closest(".clew-tab");if(!n)return;let r=n.dataset.mode;r&&r!==e()&&s(r)})}function y(s){let e=document.getElementById("clewModeSelector");e&&(e.querySelectorAll(".clew-tab").forEach(t=>{t.classList.toggle("active",t.dataset.mode===s)}),G(s))}var q={project:"Visualizes the full verification DAG for all tracked runs. Each node shows a script or file with its SHA-256 hash status \u2014 green means verified, red means the file has changed since it was recorded.",file:"Drop or select any output file from the file tree to trace its full dependency chain back to the original source data. Multiple files merge into a single DAG.",claims:"Links specific manuscript assertions (statistics, figures, tables) to the scripts and data that produced them. Define the manuscript claims before verification."};function G(s){let e=document.getElementById("clewModeInfo");e&&(e.innerHTML=q[s]??"")}function N(s,e){let t=document.querySelector(".pane-header-actions");if(!t)return;let i=t.querySelector(".clew-db-badge");i&&i.remove();let n=document.createElement("span");n.className=`clew-db-badge ${s?"clew-db-badge--found":"clew-db-badge--missing"}`;let r=s?"Records available":"Records unavailable",o=e?`${s?"Database":"Expected"}: ${e}`:"No project database";n.title=o,n.innerHTML=`<i class="fas fa-database"></i> ${r}`,t.appendChild(n)}async function k(s,e){let t=await d.getStats();if(!t.success){m(s,t.error||"Project records are unavailable");return}if(t.success&&t.data&&N(t.data.db_found??!1,t.data.db_path??null),t.success&&t.data&&t.data.total_runs>0){f(s);let n=await d.getMermaidDag({pathMode:"name"});if(n.success&&n.data?.mermaid){await u(s,n.data.mermaid);return}}let i=t.data;i&&i.total_runs>0?s.innerHTML=`
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
    `}async function P(s){f(s);let[e,t]=await Promise.all([d.listClaims(),d.getMermaidDag({claims:!0,pathMode:"name"})]);if(!e.success||!t.success){m(s,e.error||t.error||"Claim records are unavailable");return}t.success&&t.data?.mermaid&&t.data.mermaid.trim()!=="graph TD"?await u(s,t.data.mermaid):w(s,"fa-file-contract","No Claims Registered","Claims link specific manuscript assertions (statistics, figures, tables) to the source data and scripts that produced them. Define the manuscript claims before verification."),e.success&&e.data?.claims?.length&&U(s,e.data.claims)}function R(s){let e=document.createElement("span");return e.textContent=s,e.innerHTML}function U(s,e){let t={statistic:"fa-chart-bar",figure:"fa-image",table:"fa-table",text:"fa-font",value:"fa-hashtag"},i={registered:'<span class="badge badge-secondary">Registered</span>',verified:'<span class="badge badge-success">Verified</span>',mismatch:'<span class="badge badge-danger">Mismatch</span>',missing:'<span class="badge badge-warning">Missing</span>',partial:'<span class="badge badge-warning">Partial</span>'},n=e.map(o=>{let a=t[o.claim_type]||"fa-question",c=o.line_number?`${o.file_path.split("/").pop()}:L${o.line_number}`:o.file_path.split("/").pop(),l=o.claim_value?` = ${o.claim_value}`:"",p=i[o.status]||i.registered;return`<div class="claim-item">
        <i class="fas ${a} claim-type-icon"></i>
        <span class="claim-location">${R(c||"")}</span>
        <span class="claim-value">${R(l)}</span>
        ${p}
      </div>`}).join(""),r=document.createElement("div");r.className="claims-list",r.innerHTML=n,s.appendChild(r)}function H(s){w(s,"fa-crosshairs","File Trace Mode","Select any output file to trace its full dependency chain back to the original source data as a DAG. Each node shows the script and hash status \u2014 green means verified, red means the file has changed since it was recorded. Drop multiple files to see a merged DAG.")}var S=class{constructor(){g(this,"dagArea",null);g(this,"detailsPanel",null);g(this,"projectId",null);g(this,"currentMode","project");this.dagArea=document.querySelector(".dag-visualization-area"),this.detailsPanel=document.querySelector(".clew-details-content"),this.extractProjectInfo()}extractProjectInfo(){let e=document.getElementById("workspace-project-config");e&&(this.projectId=e.dataset.projectRef||e.dataset.projectId||null)}async initialize(){if(!this.projectId){console.log("[Clew] No project selected");return}A(i=>{this.currentMode=i,y(i),this.renderCurrentMode()},()=>this.currentMode),y(this.currentMode),document.getElementById("clew-file-form")?.addEventListener("submit",i=>{i.preventDefault();let n=document.querySelector("#clew-file-path")?.value.trim();n&&document.dispatchEvent(new CustomEvent("fileSelected",{detail:{path:n}}))}),this.setupEventListeners(),this.setupDropTarget();let t=new URLSearchParams(window.location.search).get("file");t?(this.switchToFileMode(),this.dagArea&&await v(this.dagArea,t,this.projectId,this.detailsPanel)):await this.renderCurrentMode()}switchToFileMode(){this.currentMode="file",y("file")}async renderCurrentMode(){if(this.dagArea){switch(this.currentMode){case"project":await k(this.dagArea,this.projectId);break;case"claims":await P(this.dagArea);break;case"file":H(this.dagArea);break}this.updateAddExamplesVisibility()}}updateAddExamplesVisibility(){if(!this.dagArea)return;let e=this.dagArea.querySelector(".clew-add-examples-btn");e&&e.addEventListener("click",()=>this.addExamples(e))}async addExamples(e){e.disabled=!0,e.innerHTML="Adding...";let t=await d.addExamples();t.success?(e.innerHTML="Added",this.showExamplesGuidance(),e.style.display="none"):(e.innerHTML="Add Examples",e.disabled=!1,console.error("[Clew] Failed to add examples:",t.error),alert(`Failed to add examples: ${t.error}`))}showExamplesGuidance(){this.dagArea&&(this.dagArea.innerHTML=`
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
    `)}setupEventListeners(){document.addEventListener("fileSelected",async e=>{let i=e.detail?.path;i&&this.dagArea&&(this.switchToFileMode(),await v(this.dagArea,i,this.projectId,this.detailsPanel))})}setupDropTarget(){this.dagArea&&(this.dagArea.addEventListener("dragover",e=>{e.preventDefault(),e.stopPropagation(),this.dagArea.classList.add("drop-target"),e.dataTransfer&&(e.dataTransfer.dropEffect="copy")}),this.dagArea.addEventListener("dragleave",e=>{e.preventDefault(),this.dagArea.classList.remove("drop-target")}),this.dagArea.addEventListener("drop",async e=>{e.preventDefault(),e.stopPropagation(),this.dagArea.classList.remove("drop-target");let t=T(e);t.length!==0&&(this.switchToFileMode(),t.length>1?await D(this.dagArea,t):await v(this.dagArea,t[0],this.projectId,this.detailsPanel))}))}};function I(){new S().initialize()}document.readyState==="loading"?document.addEventListener("DOMContentLoaded",I):I();
