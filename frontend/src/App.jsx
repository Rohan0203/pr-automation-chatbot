import React, { useCallback, useEffect, useMemo, useRef, useState } from "react"

const STARTER_CARDS = [
	{
		id: "s3",
		title: "Provision an S3 Bucket",
		description: "Launch an approval-ready S3 request with naming, policy, and location guidance.",
		prompt: "I need to create an S3 bucket for analytics exports in dev.",
		sampleUser: "Create an S3 bucket for finance exports in us-east dev.",
		sampleAssistant: "Done. I will collect the bucket details and prepare a PR-ready YAML.",
	},
	{
		id: "glue",
		title: "Create a Glue Database",
		description: "Generate a Glue DB request aligned to enterprise naming conventions and validations.",
		prompt: "I need a Glue database for customer analytics in prod.",
		sampleUser: "Create a Glue database for customer analytics in prod.",
		sampleAssistant: "I can guide you field by field and validate the naming rules before PR creation.",
	},
	{
		id: "iam",
		title: "Build an IAM Role",
		description: "Draft an IAM role request with clear ownership, purpose, and policy expectations.",
		prompt: "I need an IAM role for a nightly ETL workflow.",
		sampleUser: "Create an IAM role for a nightly ETL workflow.",
		sampleAssistant: "Prepared. I will gather trust, permissions, and ownership metadata step by step.",
	},
	{
		id: "resume",
		title: "Continue Existing Work",
		description: "Resume a previous provisioning conversation from the history panel on the left.",
		prompt: "Show me where we left off and help me continue.",
		sampleUser: "Continue my last infrastructure request.",
		sampleAssistant: "Loaded. Your previous progress is available from history and can continue from the last step.",
	},
]

function formatTime(ts) {
	if (!ts) return ""
	try {
		return new Date(ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
	} catch {
		return ""
	}
}

function escapeHtml(str) {
	const div = document.createElement("div")
	div.appendChild(document.createTextNode(str || ""))
	return div.innerHTML
}

function escapeAttr(str) {
	return (str || "")
		.replace(/&/g, "&amp;")
		.replace(/"/g, "&quot;")
		.replace(/'/g, "&#39;")
		.replace(/</g, "&lt;")
		.replace(/>/g, "&gt;")
}

function formatContent(text) {
	let html = escapeHtml(text)
	html = html.replace(/```(\w*)\n([\s\S]*?)```/g, (_, lang, code) => {
		const label = lang || "yaml"
		return `<div class="code-block"><div class="code-header"><span>${label}</span><button class="copy-btn" data-code="${escapeAttr(code.trim())}">Copy</button></div><pre>${escapeHtml(code.trim())}</pre></div>`
	})
	html = html.replace(/`([^`]+)`/g, "<code>$1</code>")
	html = html.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
	html = html.replace(/\*([^*]+)\*/g, "<em>$1</em>")
	html = html.replace(/(https?:\/\/[^\s<]+)/g, '<a href="$1" target="_blank" rel="noopener">$1</a>')
	html = html.replace(/\n/g, "<br>")
	return html
}

function MessageBubble({ message, isLatest, onOptionClick }) {
	const [selected, setSelected] = useState(new Set())

	const handleCopyClick = useCallback((event) => {
		const button = event.target.closest(".copy-btn")
		if (!button) return
		navigator.clipboard.writeText(button.dataset.code || "").then(() => {
			const original = button.textContent
			button.textContent = "Copied!"
			setTimeout(() => {
				button.textContent = original
			}, 1200)
		}).catch(() => {})
	}, [])

	const handleOptionSelect = useCallback((value) => {
		if (!message.options_multi_select) {
			onOptionClick?.(value)
			return
		}

		setSelected((current) => {
			const next = new Set(current)
			if (next.has(value)) next.delete(value)
			else next.add(value)
			return next
		})
	}, [message.options_multi_select, onOptionClick])

	const submitMultiSelect = useCallback(() => {
		if (!selected.size) return
		onOptionClick?.(Array.from(selected).join(", "))
		setSelected(new Set())
	}, [onOptionClick, selected])

	return (
		<div className={`msg msg-${message.role}`}>
			<div className="msg-bubble" onClick={handleCopyClick}>
				{message.role === "assistant"
					? <div className="markdown-body" dangerouslySetInnerHTML={{ __html: formatContent(message.content) }} />
					: message.content}
			</div>
			{message.role === "assistant" && isLatest && Array.isArray(message.options) && message.options.length > 0 && (
				<div className="options-grid">
					{message.options.map((option, index) => {
						const isSelected = selected.has(option.value)
						return (
							<button
								key={`${option.value}-${index}`}
								type="button"
								className={`option-btn${isSelected ? " selected" : ""}`}
								onClick={() => handleOptionSelect(option.value)}
								title={option.description || option.label}
							>
								<span className="option-label-row">
									{message.options_multi_select && <span className="option-check">{isSelected ? "☑" : "☐"}</span>}
									<span className="option-label">{option.label}</span>
								</span>
								{option.description && <span className="option-desc">{option.description}</span>}
							</button>
						)
					})}
					{message.options_multi_select && (
						<button type="button" className="option-btn option-submit" onClick={submitMultiSelect} disabled={!selected.size}>
							<span className="option-label">Confirm Selection</span>
						</button>
					)}
				</div>
			)}
		</div>
	)
}

export default function App() {
	const [isLoading, setIsLoading] = useState(true)
	const [isAuthenticated, setIsAuthenticated] = useState(false)
	const [githubUser, setGithubUser] = useState("")
	const [authError, setAuthError] = useState("")
	const [errorText, setErrorText] = useState("")
	const [draft, setDraft] = useState("")
	const [messages, setMessages] = useState([])
	const [chats, setChats] = useState([])
	const [currentChatId, setCurrentChatId] = useState(null)
	const [sidebarOpen, setSidebarOpen] = useState(true)
	const [historyMenuId, setHistoryMenuId] = useState(null)
	const [showTemplates, setShowTemplates] = useState(true)
	const [sending, setSending] = useState(false)
	const textareaRef = useRef(null)
	const threadEndRef = useRef(null)

	const hasActiveSession = currentChatId !== null

	const helperText = useMemo(() => {
		if (hasActiveSession) return "Session started. Continue your conversation below."
		return "Choose a MINI starter to begin quickly, or start a new chat from the history panel."
	}, [hasActiveSession])

	useEffect(() => {
		threadEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" })
	}, [messages, sending])

	useEffect(() => {
		if (!historyMenuId) return undefined
		const onDocumentClick = () => setHistoryMenuId(null)
		document.addEventListener("click", onDocumentClick)
		return () => document.removeEventListener("click", onDocumentClick)
	}, [historyMenuId])

	const api = useCallback(async (path, options = {}, userOverride = null) => {
		const headers = {
			...(options.body ? { "Content-Type": "application/json" } : {}),
			...(options.headers || {}),
		}
		const actingUser = userOverride || githubUser
		if (actingUser) headers["X-GitHub-User"] = actingUser

		const response = await fetch(path, { ...options, headers })
		if (!response.ok) {
			let message = "Request failed"
			try {
				const payload = await response.json()
				message = payload.detail || payload.error || message
			} catch {
			}
			throw new Error(message)
		}
		if (response.status === 204) return null
		return response.json()
	}, [githubUser])

	const mapMessages = useCallback((payload = []) => (
		payload.map((item) => ({
			id: String(item.id),
			role: item.role,
			content: item.content,
			created_at: item.created_at,
			options: item.metadata_json?.options || null,
			options_multi_select: Boolean(item.metadata_json?.options_multi_select),
		}))
	), [])

	const loadChat = useCallback(async (chatId, userOverride = null) => {
		if (!chatId) {
			setCurrentChatId(null)
			setMessages([])
			setShowTemplates(true)
			return
		}

		const payload = await api(`/api/chats/${chatId}/messages`, {}, userOverride)
		const nextMessages = mapMessages(payload || [])
		setCurrentChatId(String(chatId))
		setMessages(nextMessages)
		setShowTemplates(nextMessages.length === 0)
		setErrorText("")
	}, [api, mapMessages])

	const loadChats = useCallback(async (userOverride = null, preferredChatId = null) => {
		const payload = await api("/api/chats", {}, userOverride)
		const nextChats = payload?.chats || []
		setChats(nextChats)

		const selectedChatId = preferredChatId
			|| (currentChatId && nextChats.some((chat) => String(chat.id) === String(currentChatId)) ? currentChatId : null)
			|| nextChats[0]?.id

		if (selectedChatId) {
			await loadChat(selectedChatId, userOverride)
		} else {
			setCurrentChatId(null)
			setMessages([])
			setShowTemplates(true)
		}

		return nextChats
	}, [api, currentChatId, loadChat])

	useEffect(() => {
		const init = async () => {
			try {
				const params = new URLSearchParams(window.location.search)

				if (params.get("auth") === "success" && params.get("github_user")) {
					const user = params.get("github_user")
					localStorage.setItem("github_user", user)
					setGithubUser(user)
					setIsAuthenticated(true)
					window.history.replaceState({}, "", "/")
					await loadChats(user)
					return
				}

				if (params.get("auth_error")) {
					window.history.replaceState({}, "", "/")
					setAuthError("GitHub authentication failed. Please try again.")
					return
				}

				const savedUser = localStorage.getItem("github_user")
				if (!savedUser) return

				const auth = await api("/auth/me", { headers: { "X-GitHub-User": savedUser } }, savedUser)
				if (!auth?.authenticated) {
					localStorage.removeItem("github_user")
					return
				}

				setGithubUser(savedUser)
				setIsAuthenticated(true)
				await loadChats(savedUser)
			} catch {
				localStorage.removeItem("github_user")
			} finally {
				setIsLoading(false)
			}
		}

		init()
	}, [api, loadChats])

	const startNewChat = useCallback(async () => {
		try {
			setErrorText("")
			const chat = await api("/api/chats", { method: "POST" })
			setChats((current) => [chat, ...current])
			setCurrentChatId(String(chat.id))
			setMessages([])
			setDraft("")
			setShowTemplates(true)
			setHistoryMenuId(null)
			if (textareaRef.current) textareaRef.current.style.height = "auto"
		} catch (error) {
			setErrorText(error.message)
		}
	}, [api])

	const deleteChat = useCallback(async (chatId) => {
		setHistoryMenuId(null)
		if (!window.confirm("Delete this chat from history?")) return

		try {
			await api(`/api/chats/${chatId}`, { method: "DELETE" })
			const remaining = chats.filter((chat) => String(chat.id) !== String(chatId))
			setChats(remaining)

			if (String(currentChatId) === String(chatId)) {
				if (remaining.length > 0) {
					await loadChat(remaining[0].id)
				} else {
					setCurrentChatId(null)
					setMessages([])
					setShowTemplates(true)
				}
			}
		} catch (error) {
			setErrorText(error.message)
		}
	}, [api, chats, currentChatId, loadChat])

	const logout = useCallback(() => {
		localStorage.removeItem("github_user")
		setIsAuthenticated(false)
		setGithubUser("")
		setChats([])
		setMessages([])
		setDraft("")
		setCurrentChatId(null)
		setShowTemplates(true)
		setHistoryMenuId(null)
		setAuthError("")
		setErrorText("")
	}, [])

	const useStarterPrompt = useCallback(async (prompt) => {
		if (!currentChatId) {
			await startNewChat()
		}
		setDraft(prompt)
		requestAnimationFrame(() => textareaRef.current?.focus())
	}, [currentChatId, startNewChat])

	const updateComposerHeight = useCallback((value) => {
		setDraft(value)
		if (!textareaRef.current) return
		textareaRef.current.style.height = "auto"
		textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 180)}px`
	}, [])

	const sendMessage = useCallback(async (eventOrText) => {
		if (eventOrText?.preventDefault) eventOrText.preventDefault()
		const text = typeof eventOrText === "string" ? eventOrText : draft
		const trimmed = text.trim()
		if (!trimmed || sending) return

		try {
			setErrorText("")
			let workingChatId = currentChatId

			if (!workingChatId) {
				const chat = await api("/api/chats", { method: "POST" })
				workingChatId = String(chat.id)
				setChats((current) => [chat, ...current])
				setCurrentChatId(workingChatId)
			}

			setMessages((current) => [
				...current,
				{ id: `user-${Date.now()}`, role: "user", content: trimmed },
			])
			setShowTemplates(false)
			setSending(true)
			setDraft("")
			if (textareaRef.current) textareaRef.current.style.height = "auto"

			const payload = await api("/api/chat", {
				method: "POST",
				body: JSON.stringify({ message: trimmed, session_id: workingChatId }),
			})

			setMessages((current) => [
				...current,
				{
					id: `assistant-${Date.now()}`,
					role: "assistant",
					content: payload.generated_yaml && !payload.message.includes("```")
						? `${payload.message}\n\n\`\`\`yaml\n${payload.generated_yaml}\n\`\`\``
						: payload.message,
					options: payload.options || null,
					options_multi_select: Boolean(payload.options_multi_select),
				},
			])

			setChats((current) => {
				const chatId = payload.session_id || workingChatId
				const existing = current.find((chat) => String(chat.id) === String(chatId))
				const updated = {
					id: chatId,
					title: payload.chat_title || existing?.title || trimmed.slice(0, 48) || "New Chat",
					created_at: existing?.created_at || payload.updated_at || new Date().toISOString(),
					updated_at: payload.updated_at || new Date().toISOString(),
					message_count: (existing?.message_count || 0) + 2,
				}
				return [updated, ...current.filter((chat) => String(chat.id) !== String(chatId))]
			})
		} catch (error) {
			setMessages((current) => [
				...current,
				{ id: `assistant-error-${Date.now()}`, role: "assistant", content: `⚠️ ${error.message}` },
			])
			setErrorText(error.message)
		} finally {
			setSending(false)
		}
	}, [api, currentChatId, draft, sending])

	if (isLoading) {
		return (
			<div className="entry-screen">
				<div className="entry-card loading-card">
					<div className="mini-spinner" />
					<p>Loading MINI workspace...</p>
				</div>
			</div>
		)
	}

	if (!isAuthenticated) {
		return (
			<div className="entry-screen">
				<div className="entry-card">
					<div className="mini-badge">Minerva Intelligence</div>
					<h1>Welcome to MINI</h1>
					<p>Enterprise-ready agent workspace for provisioning, documentation, and PR-driven infrastructure workflows.</p>
					{authError && <div className="error-banner">{authError}</div>}
					<div className="entry-actions">
						<a className="btn-primary github-login-btn" href="/auth/github">Sign in with Cargill GitHub</a>
					</div>
				</div>
			</div>
		)
	}

	return (
		<div className="mini-shell">
			<header className="top-bar">
				<div className="top-bar-left">
					<span className="top-bar-logo">Minerva</span>
				</div>
				<div className="top-bar-right">
					<span className="top-bar-badge">
						<svg className="top-bar-user-icon" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
							<path d="M20 21C20 17.6863 16.4183 15 12 15C7.58172 15 4 17.6863 4 21" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
							<circle cx="12" cy="8" r="4" stroke="currentColor" strokeWidth="2"/>
						</svg>
						{githubUser}
					</span>
				</div>
			</header>

			<div className="mini-body">
				<aside className={`mini-sidebar ${sidebarOpen ? "" : "collapsed"}`}>
					<div className="sidebar-top">
						<button className="new-chat-btn" onClick={startNewChat}>✦ New Chat</button>
						<button type="button" className="sidebar-icon-toggle" onClick={() => setSidebarOpen((current) => !current)} aria-label="Close sidebar">
							<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
								<rect x="4" y="5" width="16" height="14" rx="2" stroke="currentColor" strokeWidth="1.8"/>
								<path d="M10 5V19" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"/>
							</svg>
						</button>
					</div>

					<div className="history-wrap">
						<div className="history-title">Chat History</div>
						{chats.length === 0 ? (
							<div className="history-empty">No conversations yet. Start a new chat.</div>
						) : (
							<ul className="history-list">
								{chats.map((chat) => (
									<li key={chat.id} className="history-row">
										<button className={`history-item ${String(currentChatId) === String(chat.id) ? "active" : ""}`} title={chat.title} onClick={() => loadChat(chat.id)}>
											<span>{chat.title}</span>
											<small>{formatTime(chat.updated_at)}</small>
										</button>
										<div className="history-actions">
											<button
												type="button"
												className="history-menu-btn"
												aria-label="Chat actions"
												onClick={(event) => {
													event.stopPropagation()
													setHistoryMenuId((current) => (String(current) === String(chat.id) ? null : String(chat.id)))
												}}
											>
												⋯
											</button>
											{String(historyMenuId) === String(chat.id) && (
												<div className="history-menu" onClick={(event) => event.stopPropagation()}>
													<button type="button" className="history-menu-delete" onClick={() => deleteChat(chat.id)}>
														Delete chat
													</button>
												</div>
											)}
										</div>
									</li>
								))}
							</ul>
						)}
					</div>

					<div className="sidebar-footer">
						<div className="user-card">
							<strong>Signed-in Workspace</strong>
							<span>Connected: {githubUser}</span>
						</div>
						<div className="user-actions">
							<button className="btn-danger" onClick={logout}>Logout</button>
						</div>
					</div>
				</aside>

				{!sidebarOpen && (
					<button type="button" className="sidebar-fab-toggle" onClick={() => setSidebarOpen(true)} aria-label="Open sidebar">
						<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
							<rect x="4" y="5" width="16" height="14" rx="2" stroke="currentColor" strokeWidth="1.8"/>
							<path d="M10 5V19" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"/>
						</svg>
					</button>
				)}

				<main className="mini-main">
					<div className="main-scroll">
						<header className="main-head">
							<h2>Welcome to world of MINI</h2>
							<p>{helperText}</p>
						</header>

						{errorText && <div className="error-banner">{errorText}</div>}

						<section className="starter-grid" aria-label="MINI starters">
							{showTemplates && STARTER_CARDS.map((card) => (
								<button key={card.id} type="button" className="starter-card" onClick={() => useStarterPrompt(card.prompt)}>
									<span className="starter-tag">Starter</span>
									<h3>{card.title}</h3>
									<p>{card.description}</p>
									<div className="starter-preview" role="presentation">
										<div className="preview-title">Example chat</div>
										<div className="bubble user-bubble">{card.sampleUser}</div>
										<div className="bubble bot-bubble">{card.sampleAssistant}</div>
									</div>
								</button>
							))}
						</section>

						<section className="chat-thread" aria-label="Conversation">
							{messages.length === 0 && !showTemplates ? (
								<div className="thread-empty">No messages yet. Start typing below.</div>
							) : (
								messages.map((message, index) => (
									<MessageBubble
										key={message.id || `${message.role}-${index}`}
										message={message}
										isLatest={index === messages.length - 1 && !sending}
										onOptionClick={sendMessage}
									/>
								))
							)}

							{sending && (
								<div className="msg msg-assistant">
									<div className="msg-bubble typing-bubble">
										<div className="typing"><span /><span /><span /></div>
									</div>
								</div>
							)}

							<div ref={threadEndRef} />
						</section>
					</div>

					<form className="composer" onSubmit={sendMessage}>
						<div className="composer-box">
							<textarea
								ref={textareaRef}
								value={draft}
								onChange={(event) => updateComposerHeight(event.target.value)}
								onKeyDown={(event) => {
									if (event.key === "Enter" && !event.shiftKey) {
										event.preventDefault()
										sendMessage()
									}
								}}
								placeholder="Start a new conversation..."
								rows={2}
							/>
							<button type="submit" aria-label="Send message" className="send-btn" disabled={sending || !draft.trim()}>
								<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" width="20" height="20">
									<path d="M22 2L11 13" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
									<path d="M22 2L15 22L11 13L2 9L22 2Z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
								</svg>
							</button>
						</div>
					</form>
				</main>
			</div>
		</div>
	)
}

