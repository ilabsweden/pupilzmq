using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using NetMQ;
using NetMQ.Sockets;

public class GazeSubscriber : MonoBehaviour
{
    // Start is called before the first frame update
    void Start()
    {
        StartCoroutine(GetGaze()); 
    }

    // Update is called once per frame
    void Update()
    {
        
    }

    // Check co-routines and deligates for Unity. 

    private IEnumerator GetGaze() {
		using (var subscriber = new SubscriberSocket("tcp://localhost:5555"))
		{
                subscriber.Subscribe("pupil/gaze");
                string topic = "";
                string message = ""; 

                while(true) {
                    bool tReceived = subscriber.TryReceiveFrameString(out topic);
                    bool mReceived = subscriber.TryReceiveFrameString(out message);

                    if (tReceived && mReceived) {
                        print(message);
                        yield return message;
                    } else {
                        //print("No message");
                        yield return "";
                    }
                }

	// 			// Process 10 updates
	// 			for (int i; i < 20; ++i)
	// 			{
	// 				using (var gazeFrame = subscriber.ReceiveFrame())
	// 				{
	// 					string gaze = gazeFrame.ReadString();
	// 					Console.WriteLine(gaze);
    //                     yield gaze;
	// 				}
	// 			}
		}

    }

    // private void ListenerWork()
    // {
    //     AsyncIO.ForceDotNet.Force();
    //     using (var subSocket = new SubscriberSocket())
    //     {
    //         subSocket.Options.ReceiveHighWatermark = 1000;
    //         subSocket.Connect($"tcp://{_host}:{_port}");
    //         subSocket.SubscribeToAnyTopic();
    //         while (!_clientCancelled)
    //         {
    //             if (!subSocket.TryReceiveFrameString(out var message)) continue;
    //             _messageQueue.Enqueue(message);
    //         }
    //         subSocket.Close();
    //     }
    //     NetMQConfig.Cleanup();
    // }
    // public void DigestMessage()
    // {
    //     while (!_messageQueue.IsEmpty)
    //     {
    //         if (_messageQueue.TryDequeue(out var message))
    //             _messageCallback(message);
    //         else
    //             break;
    //     }
    // }
}
