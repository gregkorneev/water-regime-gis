import Cocoa
import WebKit

final class AppDelegate: NSObject, NSApplicationDelegate {
    private var window: NSWindow!
    private var webView: WKWebView!
    private var backendProcess: Process?
    private let appURL = URL(string: "http://127.0.0.1:8765")!

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.regular)
        buildWindow()
        showStatus("Запуск Water Regime GIS...")

        DispatchQueue.global(qos: .userInitiated).async {
            do {
                let releaseDir = try self.releaseDirectory()
                try self.ensureLocalBackend(releaseDir: releaseDir)
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

    func applicationWillTerminate(_ notification: Notification) {
        backendProcess?.terminate()
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

    private func ensureLocalBackend(releaseDir: URL) throws {
        if backendResponds() {
            return
        }
        let python = try qgisPython()
        let script = releaseDir.appendingPathComponent("scripts/run_app.py")
        if !FileManager.default.fileExists(atPath: script.path) {
            throw ShellError(message: "В release-пакете не найден scripts/run_app.py. Скачайте полный архив Water Regime GIS из GitHub Release.")
        }
        let process = Process()
        process.executableURL = python
        process.arguments = [script.path]
        process.currentDirectoryURL = releaseDir
        var environment = ProcessInfo.processInfo.environment
        environment["WATER_REGIME_GIS_NO_BROWSER"] = "1"
        environment["WATER_REGIME_GIS_PORT"] = "8765"
        environment["WATER_REGIME_GIS_RUNTIME"] = "local-release"
        process.environment = environment
        process.standardOutput = Pipe()
        process.standardError = Pipe()
        try process.run()
        backendProcess = process
        try waitForBackend()
    }

    private func waitForBackend() throws {
        let deadline = Date().addingTimeInterval(90)
        while Date() < deadline {
            if backendResponds() {
                return
            }
            if let process = backendProcess, !process.isRunning {
                throw ShellError(message: "Локальный сервис завершился сразу после запуска. Проверьте установку QGIS.")
            }
            Thread.sleep(forTimeInterval: 1)
        }
        throw ShellError(message: "Локальный сервис не ответил за 90 секунд.")
    }

    private func backendResponds() -> Bool {
        if let (_, response) = try? URLSession.shared.synchronousData(from: appURL),
           let http = response as? HTTPURLResponse,
           (200..<500).contains(http.statusCode) {
            return true
        }
        return false
    }

    private func qgisPython() throws -> URL {
        let candidates = [
            ProcessInfo.processInfo.environment["WATER_REGIME_GIS_QGIS_PYTHON"] ?? "",
            "/Applications/QGIS.app/Contents/MacOS/python",
            "/Applications/QGIS.app/Contents/MacOS/bin/python",
            "/Applications/QGIS.app/Contents/MacOS/python3.12",
        ].filter { !$0.isEmpty }
        for path in candidates {
            if FileManager.default.fileExists(atPath: path) {
                return URL(fileURLWithPath: path)
            }
        }
        throw ShellError(message: "QGIS не найден. Установите чистый QGIS с официального сайта в /Applications/QGIS.app и откройте приложение снова.")
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
