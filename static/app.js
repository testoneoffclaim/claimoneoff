const state = {
  user: null,
  tickets: [],
  notes: [],
  search: "",
  status: "all",
};

const $ = (id) => document.getElementById(id);
const loginForm = $("loginForm");
const authPanel = $("authPanel");
const dashboard = $("dashboard");
const authError = $("authError");
const sessionInfo = $("sessionInfo");
const quickStats = $("quickStats");
const ticketList = $("ticketList");
const notifications = $("notifications");
const newTicketBtn = $("newTicketBtn");
const refreshBtn = $("refreshBtn");
const logoutBtn = $("logoutBtn");
const searchInput = $("searchInput");
const statusFilter = $("statusFilter");
const ticketModal = $("ticketModal");
const ticketForm = $("ticketForm");
const cancelTicket = $("cancelTicket");
const toast = $("toast");

function notify(message) {
  toast.textContent = message;
  toast.classList.remove("hidden");
  setTimeout(() => toast.classList.add("hidden"), 2400);
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    credentials: "same-origin",
    ...options,
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.error || "Erreur API");
  return body;
}

function filteredTickets() {
  return state.tickets.filter((ticket) => {
    const haystack = `${ticket.code} ${ticket.client_name} ${ticket.order_ref} ${ticket.type} ${ticket.description}`.toLowerCase();
    const searchMatch = haystack.includes(state.search.toLowerCase());
    const statusMatch = state.status === "all" || ticket.status === state.status;
    return searchMatch && statusMatch;
  });
}

function renderStats(tickets) {
  const opened = tickets.filter((t) => t.status !== "Résolu").length;
  const critical = tickets.filter((t) => t.priority === "Critique").length;
  const progress = tickets.filter((t) => t.status === "En-cours").length;
  const resolved = tickets.filter((t) => t.status === "Résolu").length;
  quickStats.innerHTML = `
    <div class="stat"><span>Ouverts</span><strong>${opened}</strong></div>
    <div class="stat"><span>Critiques</span><strong>${critical}</strong></div>
    <div class="stat"><span>En cours</span><strong>${progress}</strong></div>
    <div class="stat"><span>Résolus</span><strong>${resolved}</strong></div>
  `;
}

function ticketCard(ticket) {
  const adminActions =
    state.user.role === "admin"
      ? `<div class="status-row"><label>Statut</label>
        <select data-ticket-id="${ticket.id}" class="status-select">
          ${["Nouveau", "En-cours", "Résolu"].map((s) => `<option ${ticket.status === s ? "selected" : ""}>${s}</option>`).join("")}
        </select></div>`
      : "";

  return `
    <article class="ticket">
      <div class="ticket-top">
        <strong>${ticket.code} · ${ticket.type}</strong>
        <div>
          <span class="badge ${ticket.status.replace(" ", "-")}">${ticket.status}</span>
          <span class="badge ${ticket.priority}">${ticket.priority}</span>
        </div>
      </div>
      <p>Client: ${ticket.client_name} · Commande: <strong>${ticket.order_ref}</strong></p>
      <p>${ticket.description}</p>
      <small>Maj: ${new Date(ticket.updated_at).toLocaleString("fr-FR")}</small>
      ${adminActions}
    </article>
  `;
}

function bindAdminActions() {
  document.querySelectorAll(".status-select").forEach((select) => {
    select.addEventListener("change", async () => {
      try {
        await api(`/api/tickets/${select.dataset.ticketId}/status`, {
          method: "PATCH",
          body: JSON.stringify({ status: select.value }),
        });
        notify("Statut ticket mis à jour.");
        await refreshData();
      } catch (error) {
        notify(error.message);
      }
    });
  });
}

function renderTickets() {
  const scoped = filteredTickets();
  renderStats(state.tickets);
  ticketList.innerHTML = scoped.length ? scoped.map(ticketCard).join("") : '<p class="empty">Aucun ticket pour ce filtre.</p>';
  bindAdminActions();
}

function renderNotifications(items) {
  notifications.innerHTML = items.length ? items.map((n) => `<li>${n.message}</li>`).join("") : "<li>Aucune notification.</li>";
}

function renderSession() {
  authPanel.classList.add("hidden");
  dashboard.classList.remove("hidden");
  sessionInfo.classList.remove("hidden");
  sessionInfo.innerHTML = `<strong>${state.user.role === "admin" ? "Admin" : "Client"}</strong><br/>${state.user.clientName}`;
  newTicketBtn.classList.toggle("hidden", state.user.role !== "client");
}

async function refreshData() {
  refreshBtn.disabled = true;
  try {
    const [tickets, notes] = await Promise.all([api("/api/tickets"), api("/api/notifications")]);
    state.tickets = tickets;
    state.notes = notes;
    renderTickets();
    renderNotifications(notes);
  } finally {
    refreshBtn.disabled = false;
  }
}

async function boot() {
  try {
    state.user = await api("/api/me");
    renderSession();
    await refreshData();
  } catch (_error) {
    // user not logged in
  }
}

searchInput.addEventListener("input", (event) => {
  state.search = event.target.value;
  renderTickets();
});

statusFilter.addEventListener("change", (event) => {
  state.status = event.target.value;
  renderTickets();
});

refreshBtn.addEventListener("click", refreshData);

loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    await api("/api/login", {
      method: "POST",
      body: JSON.stringify({
        username: $("username").value,
        password: $("password").value,
      }),
    });
    state.user = await api("/api/me");
    authError.textContent = "";
    renderSession();
    await refreshData();
    notify("Connexion réussie.");
  } catch (error) {
    authError.textContent = error.message;
  }
});

logoutBtn.addEventListener("click", async () => {
  await api("/api/logout", { method: "POST" });
  location.reload();
});

newTicketBtn.addEventListener("click", () => ticketModal.showModal());
cancelTicket.addEventListener("click", () => ticketModal.close());

ticketForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    await api("/api/tickets", {
      method: "POST",
      body: JSON.stringify({
        type: $("ticketType").value,
        priority: $("ticketPriority").value,
        orderRef: $("ticketOrder").value,
        description: $("ticketDescription").value,
      }),
    });
    ticketForm.reset();
    ticketModal.close();
    await refreshData();
    notify("Ticket créé avec succès.");
  } catch (error) {
    notify(error.message);
  }
});

boot();
