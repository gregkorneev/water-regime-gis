import Cocoa
import WebKit

final class AppDelegate: NSObject, NSApplicationDelegate {
    private var window: NSWindow!
    private var webView: WKWebView!
    private let appURL = URL(string: "http://127.0.0.1:8765")!

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.regular)
        buildWindow()
        showStatus("Запуск Water Regime GIS...")

        DispatchQueue.global(qos: .userInitiated).async {
            do {
                let releaseDir = try self.releaseDirectory()
                try self.ensureDockerBackend(releaseDir: releaseDir)
                DispatchQueue.main.async {
                    self.webView.load(URLRequest(url: self.appURL))
                    NSApp.activate(ignoringOtherApps: true)
                }
            } catch {
                DispatchQueue.main.async {
                    self.showStatus("Не удалось запустить приложение.\n\n\(error.localizedDescription)")
                    self.showAlert(message: error.localizedDescription)
                }
            }
        }
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        true
    }

    private func buildWindow() {
        let frame = NSRect(x: 0, y: 0, width: 1280, height: 860)
        window = NSWindow(
            contentRect: frame,
            styleMask: [.titled, .closable, .miniaturizable, .resizable],
            backing: .buffered,
            defer: false
        )
        window.title = "Water Regime GIS"
        window.center()

        let configuration = WKWebViewConfiguration()
        configuration.websiteDataStore = .default()
        webView = WKWebView(frame: frame, configuration: configuration)
        window.contentView = webView
        window.makeKeyAndOrderFront(nil)
    }

    private func showStatus(_ text: String) {
        let escaped = text
            .replacingOccurrences(of: "&", with: "&amp;")
            .replacingOccurrences(of: "<", with: "&lt;")
            .replacingOccurrences(of: ">", with: "&gt;")
            .replacingOccurrences(of: "\n", with: "<br>")
        webView.loadHTMLString("""
        <!doctype html>
        <html lang="ru">
        <head>
          <meta charset="utf-8">
          <style>
            body{margin:0;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:#edf4f1;color:#13221f;display:grid;place-items:center;height:100vh}
            main{width:min(680px,calc(100vw - 48px));background:white;border:1px solid #d8e0dd;border-radius:8px;padding:28px;box-shadow:0 14px 50px rgba(19,34,31,.10)}
            h1{margin:0 0 12px;font-size:28px}
            p{font-size:17px;line-height:1.45;color:#42544f}
          </style>
        </head>
        <body><main><h1>Water Regime GIS</h1><p>\(escaped)</p></main></body>
        </html>
        """, baseURL: nil)
    }

    private func releaseDirectory() throws -> URL {
        var url = URL(fileURLWithPath: CommandLine.arguments[0]).resolvingSymlinksInPath()
        for _ in 0..<4 {
            url.deleteLastPathComponent()
        }
        return url
    }

    private func ensureDockerBackend(releaseDir: URL) throws {
        try run(["docker", "info"], cwd: releaseDir, startupHint: true)
        if runStatus(["docker", "image", "inspect", "water-regime-gis:release"], cwd: releaseDir) != 0 {
            try run(["docker", "load", "-i", "water-regime-gis-image.tar"], cwd: releaseDir, startupHint: false)
        }
        try run(["docker", "compose", "up", "-d"], cwd: releaseDir, startupHint: false)
        try waitForBackend()
    }

    private func waitForBackend() throws {
        let deadline = Date().addingTimeInterval(90)
        while Date() < deadline {
            if let (_, response) = try? URLSession.shared.synchronousData(from: appURL),
               let http = response as? HTTPURLResponse,
               (200..<500).contains(http.statusCode) {
                return
            }
            Thread.sleep(forTimeInterval: 1)
        }
        throw ShellError(message: "Локальный сервис не ответил за 90 секунд.")
    }

    private func runStatus(_ args: [String], cwd: URL) -> Int32 {
        do {
            let process = Process()
            process.executableURL = URL(fileURLWithPath: "/usr/bin/env")
            process.arguments = args
            process.currentDirectoryURL = cwd
            process.standardOutput = Pipe()
            process.standardError = Pipe()
            try process.run()
            process.waitUntilExit()
            return process.terminationStatus
        } catch {
            return 127
        }
    }

    private func run(_ args: [String], cwd: URL, startupHint: Bool) throws {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/env")
        process.arguments = args
        process.currentDirectoryURL = cwd
        let output = Pipe()
        process.standardOutput = output
        process.standardError = output
        do {
            try process.run()
            process.waitUntilExit()
        } catch {
            if startupHint {
                throw ShellError(message: "Docker Desktop не найден или не запущен. Установите/запустите Docker Desktop и откройте приложение снова.")
            }
            throw error
        }
        if process.terminationStatus != 0 {
            let data = output.fileHandleForReading.readDataToEndOfFile()
            let text = String(data: data, encoding: .utf8) ?? ""
            if startupHint {
                throw ShellError(message: "Docker Desktop не готов. Запустите Docker Desktop и откройте приложение снова.")
            }
            throw ShellError(message: text.isEmpty ? "\(args.joined(separator: " ")) failed." : text)
        }
    }

    private func showAlert(message: String) {
        let alert = NSAlert()
        alert.messageText = "Water Regime GIS"
        alert.informativeText = message
        alert.alertStyle = .warning
        alert.runModal()
    }
}

struct ShellError: LocalizedError {
    let message: String
    var errorDescription: String? { message }
}

extension URLSession {
    func synchronousData(from url: URL) throws -> (Data, URLResponse) {
        var result: Result<(Data, URLResponse), Error>!
        let semaphore = DispatchSemaphore(value: 0)
        dataTask(with: url) { data, response, error in
            if let error = error {
                result = .failure(error)
            } else {
                result = .success((data ?? Data(), response ?? URLResponse()))
            }
            semaphore.signal()
        }.resume()
        semaphore.wait()
        return try result.get()
    }
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.run()
