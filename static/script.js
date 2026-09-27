// =====================================================
// BUSINESS INTELLIGENCE SQL AGENT
// =====================================================


// =====================================================
// GET HTML ELEMENTS
// =====================================================

const questionInput = document.getElementById("question");

const askButton = document.getElementById("askButton");

const messages = document.getElementById("messages");

const scrollArea = document.getElementById("scrollArea");

const emptyState = document.getElementById("emptyState");

const historyList = document.getElementById("historyList");

const emptyHistory = document.getElementById("emptyHistory");

const clearHistoryButton =
    document.getElementById("clearHistoryButton");

const newAnalysisButton =
    document.getElementById("newAnalysisButton");

const exampleButtons =
    document.querySelectorAll(".example-question");


// =====================================================
// VARIABLES
// =====================================================

let chatHistory = [];

let activeId = null;

let isBusy = false;


// =====================================================
// BASIC HELPER
// =====================================================

function createElement(tag, className, text) {

    const element = document.createElement(tag);

    if (className) {
        element.className = className;
    }

    if (
        text !== undefined &&
        text !== null
    ) {
        element.textContent = text;
    }

    return element;
}


// =====================================================
// SCROLL TO BOTTOM
// =====================================================

function scrollToBottom() {

    requestAnimationFrame(() => {

        scrollArea.scrollTop =
            scrollArea.scrollHeight;

    });
}


// =====================================================
// HIDE EMPTY SCREEN
// =====================================================

function hideEmptyState() {

    emptyState.classList.add("hidden");
}


// =====================================================
// CHECK NUMBER
// =====================================================

function isNumeric(value) {

    if (typeof value === "number") {
        return true;
    }

    if (
        typeof value === "string" &&
        value.trim() !== "" &&
        !isNaN(Number(value))
    ) {
        return true;
    }

    return false;
}


// =====================================================
// FORMAT VALUE
// =====================================================

function formatValue(value) {

    if (
        value === null ||
        value === undefined ||
        value === ""
    ) {
        return "—";
    }


    if (typeof value === "number") {

        return value.toLocaleString(
            undefined,
            {
                maximumFractionDigits: 2
            }
        );

    }


    return String(value);
}


// =====================================================
// ADD MESSAGE
// =====================================================

function addMessage(
    sender,
    text,
    isError = false
) {

    hideEmptyState();


    const message = createElement(
        "div",
        `message ${sender}${isError ? " error" : ""}`
    );


    const label = createElement(
        "div",
        "message-label",
        sender === "user"
            ? "You"
            : "Business AI"
    );


    const content = createElement(
        "div",
        "message-content",
        text
    );


    message.appendChild(label);

    message.appendChild(content);

    messages.appendChild(message);


    scrollToBottom();
}


// =====================================================
// ADD SQL
// =====================================================

function addSQL(sql) {

    if (!sql) {
        return;
    }


    const wrapper =
        createElement(
            "div",
            "sql-wrapper"
        );


    const header =
        createElement(
            "div",
            "sql-header"
        );


    const title =
        createElement(
            "span",
            null,
            "Generated SQL"
        );


    const copyButton =
        createElement(
            "button",
            null,
            "Copy"
        );


    copyButton.type = "button";


    copyButton.addEventListener(
        "click",
        async () => {

            try {

                await navigator.clipboard.writeText(
                    sql
                );

                copyButton.textContent =
                    "Copied";

            } catch (error) {

                copyButton.textContent =
                    "Copy failed";
            }


            setTimeout(() => {

                copyButton.textContent =
                    "Copy";

            }, 1500);

        }
    );


    header.appendChild(title);

    header.appendChild(copyButton);


    const code =
        createElement(
            "pre",
            "sql-code",
            sql
        );


    wrapper.appendChild(header);

    wrapper.appendChild(code);


    messages.appendChild(wrapper);


    scrollToBottom();
}


// =====================================================
// ADD TABLE
// =====================================================

function addTable(
    columns,
    data
) {

    if (
        !columns ||
        !Array.isArray(columns) ||
        !data ||
        !Array.isArray(data) ||
        data.length === 0
    ) {
        return;
    }


    const visualization =
        createElement(
            "div",
            "visualization"
        );


    const tableScroll =
        createElement(
            "div",
            "table-scroll"
        );


    const table =
        createElement(
            "table",
            "result-table"
        );


    // -------------------------
    // TABLE HEADER
    // -------------------------

    const thead =
        document.createElement("thead");


    const headerRow =
        document.createElement("tr");


    columns.forEach(column => {

        const th =
            createElement(
                "th",
                null,
                column
            );

        headerRow.appendChild(th);

    });


    thead.appendChild(headerRow);


    // -------------------------
    // TABLE BODY
    // -------------------------

    const tbody =
        document.createElement("tbody");


    data.forEach(row => {

        const tr =
            document.createElement("tr");


        columns.forEach(column => {

            const value =
                row[column];


            const td =
                createElement(
                    "td",
                    isNumeric(value)
                        ? "is-number"
                        : null,
                    formatValue(value)
                );


            tr.appendChild(td);

        });


        tbody.appendChild(tr);

    });


    table.appendChild(thead);

    table.appendChild(tbody);


    tableScroll.appendChild(table);

    visualization.appendChild(tableScroll);

    messages.appendChild(visualization);


    scrollToBottom();
}


// =====================================================
// ADD KPI
// =====================================================

function addKPI(data) {

    if (!data) {
        return;
    }


    const visualization =
        createElement(
            "div",
            "visualization"
        );


    const card =
        createElement(
            "div",
            "kpi-card"
        );


    let entries = [];


    // Backend may return:
    //
    // {
    //     label: "Revenue",
    //     value: 12345
    // }
    //
    // OR:
    //
    // {
    //     revenue: 12345
    // }


    if (
        typeof data === "object" &&
        data.value !== undefined
    ) {

        entries = [
            [
                data.label || "Result",
                data.value
            ]
        ];

    } else if (
        Array.isArray(data)
    ) {

        entries =
            Object.entries(
                data[0] || {}
            );

    } else {

        entries =
            Object.entries(data);

    }


    entries.forEach(
        ([label, value]) => {

            const item =
                createElement(
                    "div",
                    "kpi-item"
                );


            const valueElement =
                createElement(
                    "div",
                    "kpi-value",
                    formatValue(value)
                );


            const labelElement =
                createElement(
                    "div",
                    "kpi-label",
                    label
                );


            item.appendChild(
                valueElement
            );

            item.appendChild(
                labelElement
            );


            card.appendChild(item);

        }
    );


    visualization.appendChild(card);

    messages.appendChild(
        visualization
    );


    scrollToBottom();
}


// =====================================================
// ADD CHART
// =====================================================

function addChart(visualization) {

    if (
        !visualization ||
        !Array.isArray(
            visualization.data
        )
    ) {
        return;
    }


    if (
        typeof Chart === "undefined"
    ) {

        addMessage(
            "assistant",
            "Chart library could not be loaded.",
            true
        );

        return;
    }


    const chartType =
        visualization.chart_type === "line"
            ? "line"
            : "bar";


    const wrapper =
        createElement(
            "div",
            "visualization"
        );


    const container =
        createElement(
            "div",
            "chart-container"
        );


    const canvas =
        document.createElement(
            "canvas"
        );


    container.appendChild(canvas);

    wrapper.appendChild(container);

    messages.appendChild(wrapper);


    const labels =
        visualization.data.map(
            row =>
                row[
                    visualization.label_column
                ]
        );


    const values =
        visualization.data.map(
            row =>
                Number(
                    row[
                        visualization.value_column
                    ]
                )
        );


    new Chart(
        canvas,
        {

            type: chartType,


            data: {

                labels: labels,


                datasets: [

                    {

                        label:
                            visualization.value_column,

                        data: values,


                        backgroundColor:
                            chartType === "bar"
                                ? "#4fa889"
                                : "rgba(79, 168, 137, 0.12)",


                        borderColor:
                            "#4fa889",


                        borderWidth:
                            chartType === "line"
                                ? 2
                                : 0,


                        borderRadius: 6,


                        maxBarThickness: 54,


                        pointRadius: 3,


                        pointBackgroundColor:
                            "#4fa889",


                        fill:
                            chartType === "line",


                        tension: 0.32

                    }

                ]

            },


            options: {

                responsive: true,

                maintainAspectRatio: false,


                plugins: {

                    legend: {

                        display: false

                    },


                    tooltip: {

                        backgroundColor:
                            "#0b0d10",

                        padding: 10,

                        cornerRadius: 8,

                        displayColors: false

                    }

                },


                scales: {

                    x: {

                        grid: {

                            display: false

                        },


                        border: {

                            color:
                                "#363c46"

                        },


                        ticks: {

                            color:
                                "#858b95",

                            font: {

                                size: 11

                            }

                        }

                    },


                    y: {

                        beginAtZero: true,


                        grid: {

                            color:
                                "#2b3038"

                        },


                        border: {

                            display: false

                        },


                        ticks: {

                            color:
                                "#858b95",

                            font: {

                                size: 11

                            }

                        }

                    }

                }

            }

        }
    );


    scrollToBottom();
}


// =====================================================
// DISPLAY VISUALIZATION
// =====================================================

function displayVisualization(
    visualization
) {

    if (!visualization) {
        return;
    }


    const type =
        visualization.chart_type;


    if (type === "kpi") {

        addKPI(
            visualization.data
        );

        return;
    }


    if (
        type === "bar" ||
        type === "line"
    ) {

        addChart(
            visualization
        );

        return;
    }


    if (type === "table") {

        addTable(
            visualization.columns,
            visualization.data
        );

        return;
    }
}


// =====================================================
// DISPLAY COMPLETE RESULT
// =====================================================

function renderResult(result) {

    addMessage(
        "assistant",
        result.answer ||
            "Here is what I found."
    );


    addSQL(result.sql);


    displayVisualization(
        result.visualization
    );
}


// =====================================================
// LOAD HISTORY
// =====================================================

function loadHistory() {

    try {

        const saved =
            localStorage.getItem(
                "businessAIHistory"
            );


        chatHistory =
            saved
                ? JSON.parse(saved)
                : [];


    } catch (error) {

        console.error(
            "History load error:",
            error
        );

        chatHistory = [];

    }


    renderHistory();
}


// =====================================================
// SAVE HISTORY
// =====================================================

function saveHistory(
    question,
    result
) {

    const item = {

        id: Date.now(),

        question: question,

        answer:
            result.answer ||
            "Result available",

        sql:
            result.sql ||
            "",

        visualization:
            result.visualization ||
            null,

        time:
            new Date().toISOString()

    };


    chatHistory.unshift(item);


    // Keep last 30 questions

    if (
        chatHistory.length > 30
    ) {

        chatHistory =
            chatHistory.slice(0, 30);

    }


    activeId = item.id;


    persistHistory();

    renderHistory();
}


// =====================================================
// SAVE TO LOCAL STORAGE
// =====================================================

function persistHistory() {

    try {

        localStorage.setItem(
            "businessAIHistory",
            JSON.stringify(
                chatHistory
            )
        );

    } catch (error) {

        console.error(
            "History save error:",
            error
        );

    }
}


// =====================================================
// HISTORY TIME
// =====================================================

function formatHistoryTime(time) {

    try {

        return new Date(
            time
        ).toLocaleString(
            [],
            {
                day: "2-digit",
                month: "short",
                hour: "2-digit",
                minute: "2-digit"
            }
        );

    } catch {

        return "";

    }
}


// =====================================================
// RENDER HISTORY
// =====================================================

function renderHistory() {

    historyList
        .querySelectorAll(
            ".history-item"
        )
        .forEach(
            item => item.remove()
        );


    if (
        chatHistory.length === 0
    ) {

        if (emptyHistory) {

            emptyHistory.style.display =
                "block";

        }

        return;
    }


    if (emptyHistory) {

        emptyHistory.style.display =
            "none";

    }


    chatHistory.forEach(
        item => {

            const button =
                createElement(
                    "button",
                    `history-item${
                        item.id === activeId
                            ? " active"
                            : ""
                    }`
                );


            button.type = "button";


            button.appendChild(
                createElement(
                    "div",
                    "history-question",
                    item.question
                )
            );


            button.appendChild(
                createElement(
                    "small",
                    "history-time",
                    formatHistoryTime(
                        item.time
                    )
                )
            );


            button.addEventListener(
                "click",
                () => {

                    openHistoryItem(
                        item
                    );

                }
            );


            historyList.appendChild(
                button
            );

        }
    );
}


// =====================================================
// OPEN HISTORY
// =====================================================

function openHistoryItem(item) {

    if (
        !item ||
        isBusy
    ) {
        return;
    }


    messages.innerHTML = "";


    addMessage(
        "user",
        item.question
    );


    renderResult(item);


    activeId = item.id;


    renderHistory();
}


// =====================================================
// CLEAR HISTORY
// =====================================================

function clearHistory() {

    chatHistory = [];

    activeId = null;


    persistHistory();

    renderHistory();
}


// =====================================================
// NEW ANALYSIS
// =====================================================

function newAnalysis() {

    messages.innerHTML = "";


    emptyState.classList.remove(
        "hidden"
    );


    questionInput.value = "";


    questionInput.style.height =
        "auto";


    activeId = null;


    renderHistory();


    questionInput.focus();
}


// =====================================================
// LOADING
// =====================================================

function showLoading() {

    const loading =
        createElement(
            "div",
            "loading"
        );


    loading.id =
        "loadingRow";


    const dots =
        createElement(
            "div",
            "loading-dots"
        );


    for (
        let i = 0;
        i < 3;
        i++
    ) {

        dots.appendChild(
            createElement(
                "span"
            )
        );

    }


    loading.appendChild(dots);


    loading.appendChild(
        createElement(
            "span",
            null,
            "Reading your data…"
        )
    );


    messages.appendChild(
        loading
    );


    scrollToBottom();
}


// =====================================================
// HIDE LOADING
// =====================================================

function hideLoading() {

    const loading =
        document.getElementById(
            "loadingRow"
        );


    if (loading) {

        loading.remove();

    }
}


// =====================================================
// ASK QUESTION
// =====================================================

async function askQuestion() {

    // Prevent duplicate requests

    if (isBusy) {
        return;
    }


    const question =
        questionInput.value.trim();


    // Empty question

    if (!question) {

        questionInput.focus();

        return;
    }


    // Show user question

    addMessage(
        "user",
        question
    );


    // Clear input

    questionInput.value = "";

    questionInput.style.height =
        "auto";


    isBusy = true;

    askButton.disabled = true;


    // Loading

    showLoading();


    try {

        // =============================================
        // SEND QUESTION TO FASTAPI
        // =============================================

        const response =
            await fetch(
                "/ask",
                {

                    method: "POST",

                    headers: {
                        "Content-Type":
                            "application/json"
                    },

                    body:
                        JSON.stringify({
                            question:
                                question
                        })

                }
            );


        // Server error

        if (!response.ok) {

            throw new Error(
                "Server request failed"
            );

        }


        // Convert response to JSON

        const data =
            await response.json();


        hideLoading();


        // =============================================
        // SUCCESS
        // =============================================

        if (data.success) {

            renderResult(data);

            saveHistory(
                question,
                data
            );

        }

        // =============================================
        // BACKEND ERROR
        // =============================================

        else {

            addMessage(
                "assistant",

                data.message ||
                    "I could not process that question. Try asking it in a different way.",

                true
            );

        }


    } catch (error) {

        console.error(
            "Request error:",
            error
        );


        hideLoading();


        addMessage(
            "assistant",

            "The server did not respond. Please check that the FastAPI server is running and try again.",

            true
        );


    } finally {

        hideLoading();


        isBusy = false;

        askButton.disabled = false;


        questionInput.focus();

    }
}


// =====================================================
// ENTER KEY
// =====================================================

questionInput.addEventListener(
    "keydown",
    event => {

        // Enter = send
        // Shift + Enter = new line

        if (
            event.key === "Enter" &&
            !event.shiftKey
        ) {

            event.preventDefault();

            askQuestion();

        }

    }
);


// =====================================================
// TEXTAREA AUTO RESIZE
// =====================================================

questionInput.addEventListener(
    "input",
    function () {

        this.style.height =
            "auto";


        this.style.height =
            Math.min(
                this.scrollHeight,
                140
            ) + "px";

    }
);


// =====================================================
// EXAMPLE QUESTIONS
// =====================================================

exampleButtons.forEach(
    button => {

        button.addEventListener(
            "click",
            () => {

                questionInput.value =
                    button.dataset.question ||
                    button.textContent.trim();


                questionInput.focus();


                askQuestion();

            }
        );

    }
);


// =====================================================
// CLEAR HISTORY BUTTON
// =====================================================

if (clearHistoryButton) {

    clearHistoryButton.addEventListener(
        "click",
        () => {

            if (
                chatHistory.length === 0
            ) {
                return;
            }


            const confirmed =
                confirm(
                    "Clear all saved questions?"
                );


            if (confirmed) {

                clearHistory();

            }

        }
    );

}


// =====================================================
// NEW ANALYSIS BUTTON
// =====================================================

if (newAnalysisButton) {

    newAnalysisButton.addEventListener(
        "click",
        newAnalysis
    );

}


// =====================================================
// START APPLICATION
// =====================================================

window.addEventListener(
    "load",
    () => {

        loadHistory();

        questionInput.focus();

    }
);