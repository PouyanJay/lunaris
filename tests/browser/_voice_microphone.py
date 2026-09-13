"""A generated external microphone boundary; capture, worklet and upload remain real."""


async def install_microphone(page):
    await page.add_init_script("""(() => {
      window.micStreams = [];
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
        return stream;
      };
    })();""")
