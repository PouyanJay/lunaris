"""A generated external microphone boundary; capture, worklet and upload remain real."""

from playwright.async_api import Page


async def install_microphone(page: Page) -> None:
    await page.add_init_script("""(() => {
      window.micStreams = [];
      window.micContexts = [];
      navigator.mediaDevices.getUserMedia = async () => {
        const context = new AudioContext();
        await context.resume();
        const oscillator = context.createOscillator();
        const destination = context.createMediaStreamDestination();
        oscillator.connect(destination);
        oscillator.start();
        const stream = destination.stream;
        const track = stream.getTracks()[0];
        const stop = track.stop.bind(track);
        track.stop = () => {
          if (track.readyState === 'ended') return;
          stop(); oscillator.stop(); void context.close();
        };
        window.micStreams.push(stream);
        window.micContexts.push(context);
        return stream;
      };
    })();""")
